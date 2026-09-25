from flask import Blueprint, request, jsonify
from app.models import (
    user_model, doctor_model, patient_model, appointment_model,
    diagnosis_model, notification_model
)
from app.utils.auth import login_required, admin_required, get_current_user
from app.utils.helpers import paginate_items

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    user = get_current_user()
    users = user_model.scan()
    doctors = doctor_model.get_all_doctors()
    patients = patient_model.scan()
    appointments = appointment_model.scan()

    stats = {
        'total_users': len(users),
        'total_doctors': len(doctors),
        'total_patients': len(patients),
        'total_appointments': len(appointments),
        'pending_appointments': len([a for a in appointments if a.get('Status') == 'Pending']),
        'completed_appointments': len([a for a in appointments if a.get('Status') == 'Completed']),
    }

    recent_appointments = sorted(appointments, key=lambda x: x.get('CreatedAt', ''), reverse=True)[:10]
    recent_users = sorted(users, key=lambda x: x.get('CreatedAt', ''), reverse=True)[:10]

    return jsonify({
        'user': user,
        'stats': stats,
        'recent_appointments': recent_appointments,
        'recent_users': recent_users
    }), 200


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role', '')

    all_users = user_model.scan()
    if role_filter:
        all_users = [u for u in all_users if u.get('Role') == role_filter]
    all_users.sort(key=lambda x: x.get('CreatedAt', ''), reverse=True)

    pagination = paginate_items(all_users, page)

    return jsonify({
        'users': pagination['items'],
        'pagination': pagination,
        'role_filter': role_filter,
        'total_users': len(all_users)
    }), 200


@admin_bp.route('/user/<user_id>')
@login_required
@admin_required
def user_detail(user_id):
    target_user = user_model.get_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    profile = None
    if target_user.get('Role') == 'Doctor':
        profile = doctor_model.get_by_user_id(user_id)
    elif target_user.get('Role') == 'Patient':
        profile = patient_model.get_by_user_id(user_id)

    return jsonify({
        'target_user': target_user,
        'profile': profile
    }), 200


@admin_bp.route('/appointments')
@login_required
@admin_required
def appointments():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    all_appointments = appointment_model.scan()
    if status_filter:
        all_appointments = [a for a in all_appointments if a.get('Status') == status_filter]
    all_appointments.sort(key=lambda x: (x.get('Date', ''), x.get('Time', '')), reverse=True)

    pagination = paginate_items(all_appointments, page)

    for apt in pagination['items']:
        patient = patient_model.get_by_id(apt.get('PatientID'))
        doctor = doctor_model.get_by_id(apt.get('DoctorID'))
        apt['patient_name'] = user_model.get_by_id(patient['UserID'])['Name'] if patient else 'Unknown'
        apt['doctor_name'] = user_model.get_by_id(doctor['UserID'])['Name'] if doctor else 'Unknown'

    return jsonify({
        'appointments': pagination['items'],
        'pagination': pagination,
        'status_filter': status_filter
    }), 200


@admin_bp.route('/diagnoses')
@login_required
@admin_required
def diagnoses():
    page = request.args.get('page', 1, type=int)

    all_diagnoses = diagnosis_model.scan()
    all_diagnoses.sort(key=lambda x: x.get('Date', ''), reverse=True)

    pagination = paginate_items(all_diagnoses, page)

    for diag in pagination['items']:
        patient = patient_model.get_by_id(diag.get('PatientID'))
        doctor = doctor_model.get_by_id(diag.get('DoctorID'))
        diag['patient_name'] = user_model.get_by_id(patient['UserID'])['Name'] if patient else 'Unknown'
        diag['doctor_name'] = user_model.get_by_id(doctor['UserID'])['Name'] if doctor else 'Unknown'

    return jsonify({
        'diagnoses': pagination['items'],
        'pagination': pagination
    }), 200


@admin_bp.route('/notifications')
@login_required
@admin_required
def notifications():
    page = request.args.get('page', 1, type=int)

    all_notifications = notification_model.scan()
    all_notifications.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)

    pagination = paginate_items(all_notifications, page)

    for notif in pagination['items']:
        notif_user = user_model.get_by_id(notif.get('UserID'))
        notif['user_name'] = notif_user['Name'] if notif_user else 'Unknown'
        notif['user_email'] = notif_user['Email'] if notif_user else 'Unknown'

    return jsonify({
        'notifications': pagination['items'],
        'pagination': pagination
    }), 200