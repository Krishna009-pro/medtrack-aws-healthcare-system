from flask import Blueprint, request, jsonify, session
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import login_required, patient_required, get_current_user
from app.utils.helpers import get_available_slots, validate_appointment_data, paginate_items
from app.services.sns import sns_service

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')


@patient_bp.route('/dashboard')
@login_required
@patient_required
def dashboard():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    patient = user.get('patient_profile')
    appointments = []
    notifications = []

    if patient:
        appointments = appointment_model.get_by_patient(patient['PatientID'])
        appointments.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')), reverse=True)
        notifications = notification_model.get_by_user(user['UserID'], limit=5)

    return jsonify({
        'user': user,
        'patient': patient,
        'recent_appointments': appointments[:5],
        'recent_notifications': notifications
    }), 200


@patient_bp.route('/appointments')
@login_required
@patient_required
def appointments():
    user = get_current_user()
    patient = user.get('patient_profile') if user else None
    page = request.args.get('page', 1, type=int)

    all_appointments = []
    if patient:
        all_appointments = appointment_model.get_by_patient(patient['PatientID'])
        all_appointments.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')), reverse=True)

    pagination = paginate_items(all_appointments, page)

    return jsonify({
        'patient_id': patient['PatientID'] if patient else None,
        'appointments': pagination['items'],
        'pagination': pagination
    }), 200


@patient_bp.route('/book', methods=['GET', 'POST'])
@login_required
@patient_required
def book_appointment():
    user = get_current_user()
    patient = user.get('patient_profile') if user else None
    doctors = doctor_model.get_all_doctors()

    if request.method == 'GET':
        return jsonify({
            'patient': patient,
            'available_doctors': doctors,
            'action': '/patient/book',
            'method': 'POST',
            'required_fields': ['doctor_id', 'date', 'time']
        }), 200

    payload = request.get_json(silent=True) or request.form or {}
    doctor_id = payload.get('doctor_id')
    date = payload.get('date')
    time = payload.get('time')

    errors = validate_appointment_data({
        'doctor_id': doctor_id,
        'date': date,
        'time': time
    })

    if not patient:
        errors['patient'] = 'Patient profile not found'

    if doctor_id:
        doctor = doctor_model.get_by_id(doctor_id)
        if not doctor:
            errors['doctor_id'] = 'Invalid doctor selected'
        elif not appointment_model.check_slot_available(doctor_id, date, time):
            errors['time'] = 'This time slot is no longer available'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    appointment = appointment_model.create_appointment(
        patient['PatientID'], doctor_id, date, time
    )

    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor_id and doctor else None
    doctor_name = doctor_user['Name'] if doctor_user else 'Unknown Doctor'

    sns_service.send_appointment_notification(
        user['Email'], user.get('Phone', ''),
        {'doctor_name': doctor_name, 'date': date, 'time': time, 'status': 'Pending'},
        'booking'
    )

    if doctor_user:
        sns_service.send_doctor_notification(
            doctor_user['Email'], doctor_user.get('Phone', ''),
            f'New appointment booked by {user["Name"]} for {date} at {time}',
            'New Appointment Booked'
        )

    return jsonify({
        'success': True,
        'message': 'Appointment booked successfully! You will receive a confirmation shortly.',
        'appointment': appointment
    }), 200


@patient_bp.route('/appointment/<appointment_id>')
@login_required
@patient_required
def appointment_detail(appointment_id):
    user = get_current_user()
    patient = user.get('patient_profile') if user else None
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or not patient or appointment.get('PatientID') != patient['PatientID']:
        return jsonify({'error': 'Appointment not found'}), 404

    diagnosis = diagnosis_model.get_by_appointment(appointment_id)
    doctor = doctor_model.get_by_id(appointment['DoctorID'])
    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None

    return jsonify({
        'appointment': appointment,
        'doctor': doctor,
        'doctor_user': doctor_user,
        'diagnosis': diagnosis
    }), 200


@patient_bp.route('/appointment/<appointment_id>/cancel', methods=['POST', 'PUT'])
@login_required
@patient_required
def cancel_appointment(appointment_id):
    user = get_current_user()
    patient = user.get('patient_profile') if user else None
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or not patient or appointment.get('PatientID') != patient['PatientID']:
        return jsonify({'error': 'Appointment not found'}), 404

    if appointment.get('Status') in ['Completed', 'Cancelled']:
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

    return jsonify({
        'success': True,
        'message': 'Appointment cancelled successfully',
        'appointment_id': appointment_id,
        'status': 'Cancelled'
    }), 200


@patient_bp.route('/medical-history')
@login_required
@patient_required
def medical_history():
    user = get_current_user()
    patient = user.get('patient_profile') if user else None
    diagnoses = []

    if patient:
        diagnoses = diagnosis_model.get_by_patient(patient['PatientID'])
        diagnoses.sort(key=lambda x: x.get('Date', ''), reverse=True)

    return jsonify({
        'patient': patient,
        'diagnoses': diagnoses
    }), 200


@patient_bp.route('/notifications')
@login_required
@patient_required
def notifications():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    all_notifications = notification_model.get_by_user(user['UserID']) if user else []
    pagination = paginate_items(all_notifications, page)

    return jsonify({
        'notifications': pagination['items'],
        'pagination': pagination
    }), 200


@patient_bp.route('/notification/<notification_id>/read', methods=['POST', 'PUT'])
@login_required
@patient_required
def mark_notification_read(notification_id):
    notification_model.mark_as_read(notification_id)
    return jsonify({'success': True, 'notification_id': notification_id, 'read': True}), 200


@patient_bp.route('/doctors')
@login_required
@patient_required
def doctors_list():
    doctors = doctor_model.get_all_doctors()
    doctor_profiles = []

    for doctor in doctors:
        doc_user = user_model.get_by_id(doctor['UserID'])
        if doc_user:
            doctor_profiles.append({**doctor, 'user': doc_user})

    return jsonify({
        'doctors': doctor_profiles,
        'count': len(doctor_profiles)
    }), 200


@patient_bp.route('/api/available-slots')
@login_required
@patient_required
def api_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')

    if not doctor_id or not date:
        return jsonify({'slots': []}), 200

    appointments = appointment_model.get_by_doctor_date(doctor_id, date)
    booked_slots = [a['Time'] for a in appointments if a.get('Status') in ['Pending', 'Confirmed']]
    available_slots = get_available_slots(doctor_id, date, booked_slots)

    return jsonify({'slots': available_slots}), 200