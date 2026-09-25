from datetime import datetime
from flask import Blueprint, request, jsonify, session
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import login_required, doctor_required, get_current_user
from app.utils.helpers import paginate_items, generate_time_slots
from app.services.sns import sns_service

doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')


@doctor_bp.route('/dashboard')
@login_required
@doctor_required
def dashboard():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    doctor = user.get('doctor_profile')
    appointments = []
    today_appointments = []
    upcoming = []
    notifications = []

    if doctor:
        appointments = appointment_model.get_by_doctor(doctor['DoctorID'])
        today_appointments = [a for a in appointments if a.get('Date') == datetime.now().strftime('%Y-%m-%d')]
        upcoming = [a for a in appointments if a.get('Date', '') >= datetime.now().strftime('%Y-%m-%d') and a.get('Status') in ['Pending', 'Confirmed']]
        upcoming.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')))
        notifications = notification_model.get_by_user(user['UserID'], limit=5)

    return jsonify({
        'user': user,
        'doctor': doctor,
        'today_appointments': today_appointments[:5],
        'upcoming_appointments': upcoming[:5],
        'notifications': notifications
    }), 200


@doctor_bp.route('/appointments')
@login_required
@doctor_required
def appointments():
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    all_appointments = []
    if doctor:
        all_appointments = appointment_model.get_by_doctor(doctor['DoctorID'])
        if status_filter:
            all_appointments = [a for a in all_appointments if a.get('Status') == status_filter]
        all_appointments.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')), reverse=True)

    pagination = paginate_items(all_appointments, page)

    return jsonify({
        'doctor_id': doctor['DoctorID'] if doctor else None,
        'appointments': pagination['items'],
        'pagination': pagination,
        'status_filter': status_filter
    }), 200


@doctor_bp.route('/appointment/<appointment_id>')
@login_required
@doctor_required
def appointment_detail(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or not doctor or appointment.get('DoctorID') != doctor['DoctorID']:
        return jsonify({'error': 'Appointment not found'}), 404

    patient = patient_model.get_by_id(appointment.get('PatientID'))
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None
    diagnosis = diagnosis_model.get_by_appointment(appointment_id)

    return jsonify({
        'appointment': appointment,
        'patient': patient,
        'patient_user': patient_user,
        'diagnosis': diagnosis
    }), 200


@doctor_bp.route('/appointment/<appointment_id>/update-status', methods=['POST', 'PUT'])
@login_required
@doctor_required
def update_appointment_status(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or not doctor or appointment.get('DoctorID') != doctor['DoctorID']:
        return jsonify({'error': 'Appointment not found'}), 404

    payload = request.get_json(silent=True) or request.form or {}
    new_status = payload.get('status')
    if new_status not in ['Pending', 'Confirmed', 'Completed', 'Cancelled']:
        return jsonify({'error': 'Invalid status'}), 400

    appointment_model.update_status(appointment_id, new_status)

    patient = patient_model.get_by_id(appointment.get('PatientID'))
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None
    doctor_user = user_model.get_by_id(doctor['UserID'])

    if patient_user:
        if new_status == 'Confirmed':
            sns_service.send_appointment_notification(
                patient_user['Email'], patient_user.get('Phone', ''),
                {'doctor_name': doctor_user['Name'], 'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Confirmed'},
                'confirmation'
            )
        elif new_status == 'Cancelled':
            sns_service.send_appointment_notification(
                patient_user['Email'], patient_user.get('Phone', ''),
                {'doctor_name': doctor_user['Name'], 'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Cancelled'},
                'cancellation'
            )

    return jsonify({
        'success': True,
        'message': f'Appointment status updated to {new_status}',
        'status': new_status
    }), 200


@doctor_bp.route('/appointment/<appointment_id>/diagnosis', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_diagnosis(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or not doctor or appointment.get('DoctorID') != doctor['DoctorID']:
        return jsonify({'error': 'Appointment not found'}), 404

    if request.method == 'GET':
        existing = diagnosis_model.get_by_appointment(appointment_id)
        return jsonify({
            'appointment': appointment,
            'existing_diagnosis': existing
        }), 200

    payload = request.get_json(silent=True) or request.form or {}
    report = payload.get('report', '').strip()
    if not report:
        return jsonify({'error': 'Diagnosis report is required'}), 400

    diagnosis = diagnosis_model.create_diagnosis(
        appointment_id, doctor['DoctorID'], appointment['PatientID'], report
    )
    appointment_model.update_status(appointment_id, 'Completed')

    patient = patient_model.get_by_id(appointment.get('PatientID'))
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None

    if patient_user:
        sns_service.send_diagnosis_notification(
            patient_user['Email'], patient_user.get('Phone', ''),
            {'doctor_name': user['Name'], 'date': diagnosis['Date'], 'appointment_date': appointment['Date']}
        )
    sns_service.send_doctor_notification(
        user['Email'], user.get('Phone', ''),
        f'Diagnosis submitted for patient {patient_user["Name"] if patient_user else "Unknown"}',
        'Diagnosis Submitted'
    )

    return jsonify({
        'success': True,
        'message': 'Diagnosis submitted successfully',
        'diagnosis': diagnosis
    }), 201


@doctor_bp.route('/patients')
@login_required
@doctor_required
def patients_list():
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    appointments = appointment_model.get_by_doctor(doctor['DoctorID']) if doctor else []

    patient_ids = list(set([a['PatientID'] for a in appointments]))
    patients = []
    for pid in patient_ids:
        patient = patient_model.get_by_id(pid)
        if patient:
            patient_user = user_model.get_by_id(patient['UserID'])
            if patient_user:
                patients.append({**patient, 'user': patient_user})

    return jsonify({
        'patients': patients,
        'total': len(patients)
    }), 200


@doctor_bp.route('/patient/<patient_id>/history')
@login_required
@doctor_required
def patient_history(patient_id):
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    patient = patient_model.get_by_id(patient_id)

    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    patient_user = user_model.get_by_id(patient['UserID'])
    diagnoses = diagnosis_model.get_by_patient(patient_id)
    diagnoses.sort(key=lambda x: x.get('Date', ''), reverse=True)

    appointments = appointment_model.get_by_patient(patient_id)
    if doctor:
        appointments = [a for a in appointments if a.get('DoctorID') == doctor['DoctorID']]
    appointments.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')), reverse=True)

    return jsonify({
        'patient': patient,
        'patient_user': patient_user,
        'diagnoses': diagnoses,
        'appointments': appointments
    }), 200


@doctor_bp.route('/diagnoses')
@login_required
@doctor_required
def diagnoses():
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    page = request.args.get('page', 1, type=int)

    all_diagnoses = []
    if doctor:
        all_diagnoses = diagnosis_model.get_by_doctor(doctor['DoctorID'])
        all_diagnoses.sort(key=lambda x: x.get('Date', ''), reverse=True)

    pagination = paginate_items(all_diagnoses, page)

    return jsonify({
        'diagnoses': pagination['items'],
        'pagination': pagination
    }), 200


@doctor_bp.route('/schedule')
@login_required
@doctor_required
def schedule():
    user = get_current_user()
    doctor = user.get('doctor_profile') if user else None
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    appointments = []
    if doctor:
        appointments = appointment_model.get_by_doctor_date(doctor['DoctorID'], date)
        appointments.sort(key=lambda x: x.get('Time', ''))

    all_slots = generate_time_slots()
    booked_slots = {a['Time']: a for a in appointments}

    return jsonify({
        'date': date,
        'doctor_id': doctor['DoctorID'] if doctor else None,
        'all_slots': all_slots,
        'booked_slots': booked_slots,
        'appointments': appointments
    }), 200


@doctor_bp.route('/notifications')
@login_required
@doctor_required
def notifications():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    all_notifications = notification_model.get_by_user(user['UserID']) if user else []
    pagination = paginate_items(all_notifications, page)

    return jsonify({
        'notifications': pagination['items'],
        'pagination': pagination
    }), 200


@doctor_bp.route('/notification/<notification_id>/read', methods=['POST', 'PUT'])
@login_required
@doctor_required
def mark_notification_read(notification_id):
    notification_model.mark_as_read(notification_id)
    return jsonify({'success': True, 'notification_id': notification_id, 'read': True}), 200