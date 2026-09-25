from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import session, redirect, url_for, flash, request
from app.models import user_model, doctor_model, patient_model


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        user = user_model.get_by_id(user_id)
        if not user:
            session.clear()
            flash('Your session has expired. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            user = user_model.get_by_id(user_id)
            if not user:
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('auth.login'))
            if session.get('role') not in roles or user.get('Role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('auth.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def patient_required(f):
    return role_required('Patient')(f)


def doctor_required(f):
    return role_required('Doctor')(f)


def admin_required(f):
    return role_required('Admin')(f)


def get_current_user() -> dict:
    if 'user_id' not in session:
        return None
    user = user_model.get_by_id(session['user_id'])
    if user:
        if session.get('role') == 'Doctor' or user.get('Role') == 'Doctor':
            doctor = doctor_model.get_by_user_id(user['UserID'])
            if doctor:
                user['doctor_profile'] = doctor
        elif session.get('role') == 'Patient' or user.get('Role') == 'Patient':
            patient = patient_model.get_by_user_id(user['UserID'])
            if patient:
                user['patient_profile'] = patient
    return user


def get_user_profile(user_id: str) -> dict:
    user = user_model.get_by_id(user_id)
    if not user:
        return None
    if user['Role'] == 'Doctor':
        doctor = doctor_model.get_by_user_id(user_id)
        if doctor:
            user['doctor_profile'] = doctor
    elif user['Role'] == 'Patient':
        patient = patient_model.get_by_user_id(user_id)
        if patient:
            user['patient_profile'] = patient
    return user