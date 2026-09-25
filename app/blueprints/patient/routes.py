from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import login_required, patient_required, get_current_user
from app.utils.helpers import format_date, format_time, get_available_slots, validate_appointment_data, paginate_items
from app.services.sns import sns_service

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')


@patient_bp.route('/dashboard')
@login_required
@patient_required
def dashboard():
    user = get_current_user()
    patient = user.get('patient_profile')
    appointments = []
    notifications = []

    if patient:
        appointments = appointment_model.get_by_patient(patient['PatientID'])
        appointments.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)
        notifications = notification_model.get_by_user(user['UserID'], limit=5)

    return render_template('patient/dashboard.html',
                           user=user,
                           patient=patient,
                           appointments=appointments[:5],
                           notifications=notifications,
                           format_date=format_date,
                           format_time=format_time)


@patient_bp.route('/appointments')
@login_required
@patient_required
def appointments():
    user = get_current_user()
    patient = user.get('patient_profile')
    page = request.args.get('page', 1, type=int)

    all_appointments = []
    if patient:
        all_appointments = appointment_model.get_by_patient(patient['PatientID'])
        all_appointments.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)

    pagination = paginate_items(all_appointments, page)

    return render_template('patient/appointments.html',
                           user=user,
                           patient=patient,
                           appointments=pagination['items'],
                           pagination=pagination,
                           format_date=format_date,
                           format_time=format_time)


@patient_bp.route('/book', methods=['GET', 'POST'])
@login_required
@patient_required
def book_appointment():
    user = get_current_user()
    patient = user.get('patient_profile')
    doctors = doctor_model.get_all_doctors()

    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        date = request.form.get('date')
        time = request.form.get('time')

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
            return render_template('patient/book.html',
                                   user=user,
                                   patient=patient,
                                   doctors=doctors,
                                   errors=errors,
                                   form_data=request.form,
                                   format_date=format_date)

        appointment = appointment_model.create_appointment(
            patient['PatientID'], doctor_id, date, time
        )

        doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None
        doctor_name = doctor_user['Name'] if doctor_user else 'Unknown Doctor'

        # SmartBridge Proof of Data Storage Server Log
        try:
            booking_info = {
                'booking_id': appointment['AppointmentID'],
                'user_id': user['UserID'],
                'doctor': doctor_name,
                'date': date,
                'time': time,
                'status': appointment.get('Status', 'Pending')
            }
            all_bookings = appointment_model.get_by_patient(patient['PatientID'])
            print("🎟️ Booking Added:", booking_info)
            print("📅 Appointment Added:", booking_info)
            print("📦 All Bookings:", all_bookings)
            print("📦 All Appointments:", all_bookings)
        except Exception as e:
            print(f"Booking log error: {e}")

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

        flash('Appointment booked successfully! You will receive a confirmation shortly.', 'success')
        return redirect(url_for('patient.appointments'))

    return render_template('patient/book.html',
                           user=user,
                           patient=patient,
                           doctors=doctors,
                           format_date=format_date)


@patient_bp.route('/appointment/<appointment_id>')
@login_required
@patient_required
def appointment_detail(appointment_id):
    user = get_current_user()
    patient = user.get('patient_profile')
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or appointment['PatientID'] != patient['PatientID']:
        flash('Appointment not found', 'danger')
        return redirect(url_for('patient.appointments'))

    diagnosis = diagnosis_model.get_by_appointment(appointment_id)
    doctor = doctor_model.get_by_id(appointment['DoctorID'])
    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None

    return render_template('patient/appointment_detail.html',
                           user=user,
                           patient=patient,
                           appointment=appointment,
                           diagnosis=diagnosis,
                           doctor=doctor,
                           doctor_user=doctor_user,
                           format_date=format_date,
                           format_time=format_time)


@patient_bp.route('/appointment/<appointment_id>/cancel', methods=['POST'])
@login_required
@patient_required
def cancel_appointment(appointment_id):
    user = get_current_user()
    patient = user.get('patient_profile')
    appointment = appointment_model.get_by_id(appointment_id)

    if not appointment or appointment['PatientID'] != patient['PatientID']:
        flash('Appointment not found', 'danger')
        return redirect(url_for('patient.appointments'))

    if appointment['Status'] in ['Completed', 'Cancelled']:
        flash('Cannot cancel this appointment', 'warning')
        return redirect(url_for('patient.appointment_detail', appointment_id=appointment_id))

    appointment_model.update_status(appointment_id, 'Cancelled')

    doctor = doctor_model.get_by_id(appointment['DoctorID'])
    doctor_user = user_model.get_by_id(doctor['UserID']) if doctor else None

    sns_service.send_appointment_notification(
        user['Email'], user.get('Phone', ''),
        {'doctor_name': doctor_user['Name'] if doctor_user else 'Unknown Doctor',
         'date': appointment['Date'], 'time': appointment['Time'], 'status': 'Cancelled'},
        'cancellation'
    )

    flash('Appointment cancelled successfully', 'success')
    return redirect(url_for('patient.appointments'))


@patient_bp.route('/medical-history')
@login_required
@patient_required
def medical_history():
    user = get_current_user()
    patient = user.get('patient_profile')
    diagnoses = []

    if patient:
        diagnoses = diagnosis_model.get_by_patient(patient['PatientID'])
        diagnoses.sort(key=lambda x: x['Date'], reverse=True)

    return render_template('patient/medical_history.html',
                           user=user,
                           patient=patient,
                           diagnoses=diagnoses,
                           format_date=format_date)


@patient_bp.route('/notifications')
@login_required
@patient_required
def notifications():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    all_notifications = notification_model.get_by_user(user['UserID'])
    pagination = paginate_items(all_notifications, page)

    return render_template('patient/notifications.html',
                           user=user,
                           notifications=pagination['items'],
                           pagination=pagination)


@patient_bp.route('/notification/<notification_id>/read', methods=['POST'])
@login_required
@patient_required
def mark_notification_read(notification_id):
    notification_model.mark_as_read(notification_id)
    return jsonify({'success': True})


@patient_bp.route('/doctors')
@login_required
@patient_required
def doctors_list():
    user = get_current_user()
    doctors = doctor_model.get_all_doctors()
    doctor_profiles = []

    for doctor in doctors:
        doc_user = user_model.get_by_id(doctor['UserID'])
        if doc_user:
            doctor_profiles.append({**doctor, 'user': doc_user})

    return render_template('patient/doctors.html',
                           user=user,
                           doctors=doctor_profiles)


@patient_bp.route('/api/available-slots')
@login_required
@patient_required
def api_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')

    if not doctor_id or not date:
        return jsonify({'slots': []})

    appointments = appointment_model.get_by_doctor_date(doctor_id, date)
    booked_slots = [a['Time'] for a in appointments if a['Status'] in ['Pending', 'Confirmed']]
    available_slots = get_available_slots(doctor_id, date, booked_slots)

    return jsonify({'slots': available_slots})