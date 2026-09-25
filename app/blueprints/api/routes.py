from flask import Blueprint, request, jsonify, session
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import hash_password, verify_password, login_required
from app.utils.helpers import validate_appointment_data, get_available_slots
from app.services.sns import sns_service
from functools import wraps

api_bp = Blueprint('api', __name__, url_prefix='/api')


def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def api_role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required'}), 401
            if session.get('role') not in roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@api_bp.route('/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON data required'}), 400

    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'Patient')
    phone = data.get('phone', '').strip()

    errors = {}
    if not email:
        errors['email'] = 'Email is required'
    if not name:
        errors['name'] = 'Name is required'
    if not password:
        errors['password'] = 'Password is required'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters'
    if role not in ['Patient', 'Doctor']:
        errors['role'] = 'Invalid role selected'

    if user_model.get_by_email(email):
        errors['email'] = 'Email already registered'

    if errors:
        return jsonify({'errors': errors}), 400

    password_hash = hash_password(password)
    user = user_model.create_user(email, name, password_hash, role, phone)

    if role == 'Doctor':
        specialization = data.get('specialization', '').strip()
        experience = data.get('experience', 0)
        if specialization:
            doctor_model.create_doctor(user['UserID'], specialization, experience)
    elif role == 'Patient':
        age = data.get('age', 0)
        medical_history = data.get('medical_history', '').strip()
        patient_model.create_patient(user['UserID'], age, medical_history)

    return jsonify({
        'message': 'Registration successful',
        'user': {
            'user_id': user['UserID'],
            'email': user['Email'],
            'name': user['Name'],
            'role': user['Role']
        }
    }), 201


@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON data required'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = user_model.get_by_email(email)
    if not user or not verify_password(password, user['Password']):
        return jsonify({'error': 'Invalid email or password'}), 401

    session['user_id'] = user['UserID']
    session['email'] = user['Email']
    session['name'] = user['Name']
    session['role'] = user['Role']

    return jsonify({
        'message': 'Login successful',
        'user': {
            'user_id': user['UserID'],
            'email': user['Email'],
            'name': user['Name'],
            'role': user['Role']
        }
    })


@api_bp.route('/auth/logout', methods=['POST'])
@api_login_required
def api_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@api_bp.route('/auth/me', methods=['GET'])
@api_login_required
def api_me():
    user_id = session['user_id']
    user = user_model.get_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    profile = None
    if user['Role'] == 'Doctor':
        profile = doctor_model.get_by_user_id(user_id)
    elif user['Role'] == 'Patient':
        profile = patient_model.get_by_user_id(user_id)

    return jsonify({
        'user': {
            'user_id': user['UserID'],
            'email': user['Email'],
            'name': user['Name'],
            'role': user['Role'],
            'phone': user.get('Phone', '')
        },
        'profile': profile
    })


@api_bp.route('/doctors', methods=['GET'])
@api_login_required
def api_get_doctors():
    doctors = doctor_model.get_all_doctors()
    result = []
    for doctor in doctors:
        doc_user = user_model.get_by_id(doctor['UserID'])
        if doc_user:
            result.append({
                'doctor_id': doctor['DoctorID'],
                'name': doc_user['Name'],
                'email': doc_user['Email'],
                'specialization': doctor['Specialization'],
                'experience': doctor['Experience']
            })
    return jsonify({'doctors': result})


@api_bp.route('/doctors/<doctor_id>/slots', methods=['GET'])
@api_login_required
def api_get_doctor_slots(doctor_id):
    date = request.args.get('date')
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400

    appointments = appointment_model.get_by_doctor_date(doctor_id, date)
    booked_slots = [a['Time'] for a in appointments if a['Status'] in ['Pending', 'Confirmed']]
    available_slots = get_available_slots(doctor_id, date, booked_slots)

    return jsonify({'date': date, 'available_slots': available_slots})


@api_bp.route('/appointments', methods=['GET', 'POST'])
@api_login_required
def api_appointments():
    user_id = session['user_id']
    user = user_model.get_by_id(user_id)

    if request.method == 'GET':
        if user['Role'] == 'Patient':
            patient = patient_model.get_by_user_id(user_id)
            if not patient:
                return jsonify({'appointments': []})
            appointments = appointment_model.get_by_patient(patient['PatientID'])
        elif user['Role'] == 'Doctor':
            doctor = doctor_model.get_by_user_id(user_id)
            if not doctor:
                return jsonify({'appointments': []})
            appointments = appointment_model.get_by_doctor(doctor['DoctorID'])
        else:
            appointments = appointment_model.scan()

        appointments.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)
        return jsonify({'appointments': appointments})

    if user['Role'] != 'Patient':
        return jsonify({'error': 'Only patients can book appointments'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON data required'}), 400

    patient = patient_model.get_by_user_id(user_id)
    if not patient:
        return jsonify({'error': 'Patient profile not found'}), 404

    errors = validate_appointment_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    doctor_id = data['doctor_id']
    date = data['date']
    time = data['time']

    if not appointment_model.check_slot_available(doctor_id, date, time):
        return jsonify({'error': 'Time slot no longer available'}), 409

    appointment = appointment_model.create_appointment(patient['PatientID'], doctor_id, date, time)

    doctor = doctor_model.get_by_id(doctor_id)
    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None

    if doctor_user:
        sns_service.send_appointment_notification(
            user['Email'], user.get('Phone', ''),
            {'doctor_name': doctor_user['Name'], 'date': date, 'time': time, 'status': 'Pending'},
            'booking'
        )
        sns_service.send_doctor_notification(
            doctor_user['Email'], doctor_user.get('Phone', ''),
            f'New appointment booked by {user["Name"]} for {date} at {time}',
            'New Appointment Booked'
        )

    return jsonify({
        'message': 'Appointment booked successfully',
        'appointment': appointment
    }), 201


@api_bp.route('/appointments/<appointment_id>', methods=['GET'])
@api_login_required
def api_get_appointment(appointment_id):
    appointment = appointment_model.get_by_id(appointment_id)
    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404

    user_id = session['user_id']
    user = user_model.get_by_id(user_id)

    if user['Role'] == 'Patient':
        patient = patient_model.get_by_user_id(user_id)
        if not patient or appointment['PatientID'] != patient['PatientID']:
            return jsonify({'error': 'Access denied'}), 403
    elif user['Role'] == 'Doctor':
        doctor = doctor_model.get_by_user_id(user_id)
        if not doctor or appointment['DoctorID'] != doctor['DoctorID']:
            return jsonify({'error': 'Access denied'}), 403

    diagnosis = diagnosis_model.get_by_appointment(appointment_id)
    patient = patient_model.get_by_id(appointment['PatientID'])
    doctor = doctor_model.get_by_id(appointment['DoctorID'])

    return jsonify({
        'appointment': appointment,
        'diagnosis': diagnosis,
        'patient_name': user_model.get_by_id(patient['UserID'])['Name'] if patient else None,
        'doctor_name': user_model.get_by_id(doctor['UserID'])['Name'] if doctor else None
    })


@api_bp.route('/appointments/<appointment_id>/cancel', methods=['POST'])
@api_login_required
def api_cancel_appointment(appointment_id):
    appointment = appointment_model.get_by_id(appointment_id)
    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404

    user_id = session['user_id']
    user = user_model.get_by_id(user_id)

    if user['Role'] == 'Patient':
        patient = patient_model.get_by_user_id(user_id)
        if not patient or appointment['PatientID'] != patient['PatientID']:
            return jsonify({'error': 'Access denied'}), 403
    else:
        return jsonify({'error': 'Only patients can cancel appointments'}), 403

    if appointment['Status'] in ['Completed', 'Cancelled']:
        return jsonify({'error': 'Cannot cancel this appointment'}), 400

    appointment_model.update_status(appointment_id, 'Cancelled')

    doctor = doctor_model.get_by_id(appointment['DoctorID'])
    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None

    sns_service.send_appointment_notification(
        user['Email'], user.get('Phone', ''),
        {'doctor_name': doctor_user['Name'] if doctor_user else 'Unknown Doctor',
         'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Cancelled'},
        'cancellation'
    )

    return jsonify({'message': 'Appointment cancelled successfully'})


@api_bp.route('/appointments/<appointment_id>/status', methods=['PUT'])
@api_role_required('Doctor', 'Admin')
def api_update_appointment_status(appointment_id):
    appointment = appointment_model.get_by_id(appointment_id)
    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404

    user_id = session['user_id']
    user = user_model.get_by_id(user_id)

    if user['Role'] == 'Doctor':
        doctor = doctor_model.get_by_user_id(user_id)
        if not doctor or appointment['DoctorID'] != doctor['DoctorID']:
            return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON data required'}), 400

    new_status = data.get('status')
    if new_status not in ['Pending', 'Confirmed', 'Completed', 'Cancelled']:
        return jsonify({'error': 'Invalid status'}), 400

    appointment_model.update_status(appointment_id, new_status)

    patient = patient_model.get_by_id(appointment['PatientID'])
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None
    doctor_user = user_model.get_by_id(user_id)

    if new_status == 'Confirmed' and patient_user:
        sns_service.send_appointment_notification(
            patient_user['Email'], patient_user.get('Phone', ''),
            {'doctor_name': doctor_user['Name'], 'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Confirmed'},
            'confirmation'
        )
    elif new_status == 'Cancelled' and patient_user:
        sns_service.send_appointment_notification(
            patient_user['Email'], patient_user.get('Phone', ''),
            {'doctor_name': doctor_user['Name'], 'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Cancelled'},
            'cancellation'
        )

    return jsonify({'message': f'Appointment status updated to {new_status}'})


@api_bp.route('/diagnoses', methods=['GET', 'POST'])
@api_login_required
def api_diagnoses():
    user_id = session['user_id']
    user = user_model.get_by_id(user_id)

    if request.method == 'GET':
        if user['Role'] == 'Patient':
            patient = patient_model.get_by_user_id(user_id)
            if not patient:
                return jsonify({'diagnoses': []})
            diagnoses = diagnosis_model.get_by_patient(patient['PatientID'])
        elif user['Role'] == 'Doctor':
            doctor = doctor_model.get_by_user_id(user_id)
            if not doctor:
                return jsonify({'diagnoses': []})
            diagnoses = diagnosis_model.get_by_doctor(doctor['DoctorID'])
        else:
            diagnoses = diagnosis_model.scan()

        diagnoses.sort(key=lambda x: x['Date'], reverse=True)
        return jsonify({'diagnoses': diagnoses})

    if user['Role'] != 'Doctor':
        return jsonify({'error': 'Only doctors can create diagnoses'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON data required'}), 400

    appointment_id = data.get('appointment_id')
    report = data.get('report', '').strip()

    if not appointment_id or not report:
        return jsonify({'error': 'appointment_id and report are required'}), 400

    appointment = appointment_model.get_by_id(appointment_id)
    if not appointment:
        return jsonify({'error': 'Appointment not found'}), 404

    doctor = doctor_model.get_by_user_id(user_id)
    if not doctor or appointment['DoctorID'] != doctor['DoctorID']:
        return jsonify({'error': 'Access denied'}), 403

    if appointment['Status'] != 'Completed':
        return jsonify({'error': 'Can only add diagnosis for completed appointments'}), 400

    existing_diagnosis = diagnosis_model.get_by_appointment(appointment_id)
    if existing_diagnosis:
        return jsonify({'error': 'Diagnosis already exists for this appointment'}), 409

    patient = patient_model.get_by_id(appointment['PatientID'])
    diagnosis = diagnosis_model.create_diagnosis(
        appointment_id, doctor['DoctorID'], patient['PatientID'], report
    )

    appointment_model.update_status(appointment_id, 'Completed')

    patient_user = user_model.get_by_id(patient['UserID'])
    sns_service.send_diagnosis_notification(
        patient_user['Email'], patient_user.get('Phone', ''),
        {'doctor_name': user['Name'], 'date': diagnosis['Date'], 'appointment_date': appointment['Date']}
    )

    return jsonify({
        'message': 'Diagnosis submitted successfully',
        'diagnosis': diagnosis
    }), 201


@api_bp.route('/notifications', methods=['GET'])
@api_login_required
def api_notifications():
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    notifications = notification_model.get_by_user(user_id, limit=limit)
    return jsonify({'notifications': notifications})


@api_bp.route('/notifications/<notification_id>/read', methods=['PUT'])
@api_login_required
def api_mark_notification_read(notification_id):
    notification_model.mark_as_read(notification_id)
    return jsonify({'message': 'Notification marked as read'})