from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import login_required, doctor_required, get_current_user
from app.utils.helpers import format_date, format_time, paginate_items
from app.services.sns import sns_service

doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')


@doctor_bp.route('/dashboard')
@login_required
@doctor_required
def dashboard():
    user = get_current_user()
    doctor = user.get('doctor_profile')
    appointments = []
    notifications = []

    if doctor:
        appointments = appointment_model.get_by_doctor(doctor['DoctorID'])
        today = format_date(datetime.now().strftime('%Y-%m-%d'))
        today_appointments = [a for a in appointments if a['Date'] == datetime.now().strftime('%Y-%m-%d')]
        upcoming = [a for a in appointments if a['Date'] >= datetime.now().strftime('%Y-%m-%d') and a['Status'] in ['Pending', 'Confirmed']]
        upcoming.sort(key=lambda x: (x['Date'], x['Time']))
        notifications = notification_model.get_by_user(user['UserID'], limit=5)

    return render_template('doctor/dashboard.html',
                           user=user,
                           doctor=doctor,
                           today_appointments=today_appointments[:5],
                           upcoming_appointments=upcoming[:5],
                           notifications=notifications,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/appointments')
@login_required
@doctor_required
def appointments():
    user = get_current_user()
    doctor = user.get('doctor_profile')
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    all_appointments = []
    if doctor:
        all_appointments = appointment_model.get_by_doctor(doctor['DoctorID'])
        if status_filter:
            all_appointments = [a for a in all_appointments if a['Status'] == status_filter]
        all_appointments.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)

    pagination = paginate_items(all_appointments, page)

    return render_template('doctor/appointments.html',
                           user=user,
                           doctor=doctor,
                           appointments=pagination['items'],
                           pagination=pagination,
                           status_filter=status_filter,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/appointment/<appointment_id>')
@login_required
@doctor_required
def appointment_detail(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile')
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or appointment['DoctorID'] != doctor['DoctorID']:
        flash('Appointment not found', 'danger')
        return redirect(url_for('doctor.appointments'))

    patient = patient_model.get_by_id(appointment['PatientID'])
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None
    diagnosis = diagnosis_model.get_by_appointment(appointment_id)

    return render_template('doctor/appointment_detail.html',
                           user=user,
                           doctor=doctor,
                           appointment=appointment,
                           patient=patient,
                           patient_user=patient_user,
                           diagnosis=diagnosis,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/appointment/<appointment_id>/update-status', methods=['POST'])
@login_required
@doctor_required
def update_appointment_status(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile')
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or appointment['DoctorID'] != doctor['DoctorID']:
        flash('Appointment not found', 'danger')
        return redirect(url_for('doctor.appointments'))

    new_status = request.form.get('status')
    if new_status not in ['Pending', 'Confirmed', 'Completed', 'Cancelled']:
        flash('Invalid status', 'danger')
        return redirect(url_for('doctor.appointment_detail', appointment_id=appointment_id))

    appointment_model.update_status(appointment_id, new_status)

    patient = patient_model.get_by_id(appointment['PatientID'])
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None
    doctor_user = user_model.get_by_id(doctor['UserID'])

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

    flash(f'Appointment status updated to {new_status}', 'success')
    return redirect(url_for('doctor.appointment_detail', appointment_id=appointment_id))


@doctor_bp.route('/appointment/<appointment_id>/diagnosis', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_diagnosis(appointment_id):
    user = get_current_user()
    doctor = user.get('doctor_profile')
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or appointment['DoctorID'] != doctor['DoctorID']:
        flash('Appointment not found', 'danger')
        return redirect(url_for('doctor.appointments'))

    if appointment['Status'] != 'Completed':
        flash('Can only add diagnosis for completed appointments', 'warning')
        return redirect(url_for('doctor.appointment_detail', appointment_id=appointment_id))

    existing_diagnosis = diagnosis_model.get_by_appointment(appointment_id)
    if existing_diagnosis:
        flash('Diagnosis already exists for this appointment', 'warning')
        return redirect(url_for('doctor.appointment_detail', appointment_id=appointment_id))

    patient = patient_model.get_by_id(appointment['PatientID'])
    patient_user = user_model.get_by_id(patient['UserID']) if patient else None

    if request.method == 'POST':
        report = request.form.get('report', '').strip()

        if not report:
            flash('Diagnosis report is required', 'danger')
            return render_template('doctor/create_diagnosis.html',
                                   user=user,
                                   doctor=doctor,
                                   appointment=appointment,
                                   patient=patient,
                                   patient_user=patient_user,
                                   format_date=format_date,
                                   format_time=format_time)

        diagnosis = diagnosis_model.create_diagnosis(
            appointment_id, doctor['DoctorID'], patient['PatientID'], report
        )

        appointment_model.update_status(appointment_id, 'Completed')

        # SmartBridge Proof of Data Storage Server Log
        try:
            diag_info = {
                'diagnosis_id': diagnosis['DiagnosisID'],
                'appointment_id': appointment_id,
                'doctor_id': doctor['DoctorID'],
                'patient_id': patient['PatientID'],
                'report': report,
                'date': diagnosis.get('Date')
            }
            all_diagnoses = diagnosis_model.scan()
            print("🩺 Diagnosis Added:", diag_info)
            print("📦 All Diagnoses:", all_diagnoses)
        except Exception as e:
            print(f"Diagnosis log error: {e}")

        sns_service.send_diagnosis_notification(
            patient_user['Email'], patient_user.get('Phone', ''),
            {'doctor_name': user['Name'], 'date': diagnosis['Date'], 'appointment_date': appointment['Date']}
        )

        sns_service.send_doctor_notification(
            user['Email'], user.get('Phone', ''),
            f'Diagnosis submitted for patient {patient_user["Name"]}',
            'Diagnosis Submitted'
        )

        flash('Diagnosis submitted successfully', 'success')
        return redirect(url_for('doctor.appointment_detail', appointment_id=appointment_id))

    return render_template('doctor/create_diagnosis.html',
                           user=user,
                           doctor=doctor,
                           appointment=appointment,
                           patient=patient,
                           patient_user=patient_user,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/patients')
@login_required
@doctor_required
def patients_list():
    user = get_current_user()
    doctor = user.get('doctor_profile')
    appointments = appointment_model.get_by_doctor(doctor['DoctorID']) if doctor else []

    patient_ids = list(set([a['PatientID'] for a in appointments]))
    patients = []
    for pid in patient_ids:
        patient = patient_model.get_by_id(pid)
        if patient:
            patient_user = user_model.get_by_id(patient['UserID'])
            if patient_user:
                patients.append({**patient, 'user': patient_user})

    return render_template('doctor/patients.html',
                           user=user,
                           doctor=doctor,
                           patients=patients)


@doctor_bp.route('/patient/<patient_id>/history')
@login_required
@doctor_required
def patient_history(patient_id):
    user = get_current_user()
    doctor = user.get('doctor_profile')
    patient = patient_model.get_by_id(patient_id)

    if not patient:
        flash('Patient not found', 'danger')
        return redirect(url_for('doctor.patients_list'))

    patient_user = user_model.get_by_id(patient['UserID'])
    diagnoses = diagnosis_model.get_by_patient(patient_id)
    diagnoses.sort(key=lambda x: x['Date'], reverse=True)

    appointments = appointment_model.get_by_patient(patient_id)
    appointments = [a for a in appointments if a['DoctorID'] == doctor['DoctorID']]
    appointments.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)

    return render_template('doctor/patient_history.html',
                           user=user,
                           doctor=doctor,
                           patient=patient,
                           patient_user=patient_user,
                           diagnoses=diagnoses,
                           appointments=appointments,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/diagnoses')
@login_required
@doctor_required
def diagnoses():
    user = get_current_user()
    doctor = user.get('doctor_profile')
    page = request.args.get('page', 1, type=int)

    all_diagnoses = []
    if doctor:
        all_diagnoses = diagnosis_model.get_by_doctor(doctor['DoctorID'])
        all_diagnoses.sort(key=lambda x: x['Date'], reverse=True)

    pagination = paginate_items(all_diagnoses, page)

    return render_template('doctor/diagnoses.html',
                           user=user,
                           doctor=doctor,
                           diagnoses=pagination['items'],
                           pagination=pagination,
                           format_date=format_date)


@doctor_bp.route('/schedule')
@login_required
@doctor_required
def schedule():
    from datetime import datetime
    user = get_current_user()
    doctor = user.get('doctor_profile')
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    appointments = []
    if doctor:
        appointments = appointment_model.get_by_doctor_date(doctor['DoctorID'], date)
        appointments.sort(key=lambda x: x['Time'])

    from app.utils.helpers import generate_time_slots
    all_slots = generate_time_slots()
    booked_slots = {a['Time']: a for a in appointments}

    return render_template('doctor/schedule.html',
                           user=user,
                           doctor=doctor,
                           date=date,
                           appointments=appointments,
                           all_slots=all_slots,
                           booked_slots=booked_slots,
                           format_date=format_date,
                           format_time=format_time)


@doctor_bp.route('/notifications')
@login_required
@doctor_required
def notifications():
    user = get_current_user()
    doctor = user.get('doctor_profile')
    page = request.args.get('page', 1, type=int)
    all_notifications = notification_model.get_by_user(user['UserID']) if user else []
    pagination = paginate_items(all_notifications, page)

    return render_template('doctor/notifications.html',
                           user=user,
                           doctor=doctor,
                           notifications=pagination['items'],
                           pagination=pagination)


@doctor_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
@doctor_required
def mark_notification_read(notification_id):
    notification_model.mark_as_read(notification_id)
    return jsonify({'success': True})