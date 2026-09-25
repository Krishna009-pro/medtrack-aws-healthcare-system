from flask import Blueprint, request, session, jsonify
from app.models import user_model, doctor_model, patient_model
from app.utils.auth import hash_password, verify_password
from app.config import Config

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return jsonify({
            'message': 'Create Account or Register',
            'action': '/auth/register',
            'method': 'POST',
            'required_fields': ['email', 'name', 'password', 'confirm_password', 'role', 'phone'],
            'optional_doctor_fields': ['specialization', 'experience'],
            'optional_patient_fields': ['age', 'medical_history']
        })

    payload = request.get_json(silent=True) or request.form or {}
    email = payload.get('email', '').strip().lower()
    name = payload.get('name', '').strip()
    password = payload.get('password', '')
    confirm_password = payload.get('confirm_password', '')
    role = payload.get('role', 'Patient')
    phone = payload.get('phone', '').strip()

    errors = {}
    if not email:
        errors['email'] = 'Email is required'
    if not name:
        errors['name'] = 'Name is required'
    if not password:
        errors['password'] = 'Password is required'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters'
    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match'
    if role not in ['Patient', 'Doctor']:
        errors['role'] = 'Invalid role selected'

    if user_model.get_by_email(email):
        errors['email'] = 'Email already registered'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    password_hash = hash_password(password)
    user = user_model.create_user(email, name, password_hash, role, phone)

    if role == 'Doctor':
        specialization = payload.get('specialization', '').strip()
        experience = payload.get('experience', 0)
        try:
            experience = int(experience)
        except (ValueError, TypeError):
            experience = 0
        if specialization:
            doctor_model.create_doctor(user['UserID'], specialization, experience)
    elif role == 'Patient':
        age = payload.get('age', 0)
        medical_history = payload.get('medical_history', '').strip()
        try:
            age = int(age)
        except (ValueError, TypeError):
            age = 0
        patient_model.create_patient(user['UserID'], age, medical_history)

    return jsonify({
        'success': True,
        'message': 'Registration successful! Please log in.',
        'user': {
            'UserID': user['UserID'],
            'Email': user['Email'],
            'Name': user['Name'],
            'Role': user['Role'],
            'Phone': user.get('Phone', '')
        }
    }), 200


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return jsonify({
            'message': 'Sign in to your MedTrack account or Welcome Back',
            'action': '/auth/login',
            'method': 'POST',
            'fields': ['email', 'password']
        })

    payload = request.get_json(silent=True) or request.form or {}
    email = payload.get('email', '').strip().lower()
    password = payload.get('password', '')
    remember = payload.get('remember') in ['on', True, 'true', 1, '1']

    user = user_model.get_by_email(email)
    if not user or not verify_password(password, user['Password']):
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401

    session['user_id'] = user['UserID']
    session['email'] = user['Email']
    session['name'] = user['Name']
    session['role'] = user['Role']
    session['user'] = {
        'id': user['UserID'],
        'name': user['Name'],
        'email': user['Email'],
        'role': user['Role']
    }
    session.permanent = remember

    mode_str = 'Local Mode' if not Config.is_aws_mode() else 'AWS Mode'
    return jsonify({
        'success': True,
        'message': f'Welcome Back, {user["Name"]}!',
        'role': user['Role'],
        'mode': mode_str,
        'user': {
            'id': user['UserID'],
            'name': user['Name'],
            'email': user['Email'],
            'role': user['Role'],
            'phone': user.get('Phone', '')
        }
    }), 200


@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    session.clear()
    return jsonify({
        'success': True,
        'message': 'You have been logged out.'
    }), 200


@auth_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session and 'user' not in session:
        return jsonify({'error': 'Authentication required', 'message': 'Please log in'}), 401

    role = session.get('role')
    return jsonify({
        'status': 'authenticated',
        'user_id': session.get('user_id'),
        'role': role,
        'name': session.get('name'),
        'email': session.get('email'),
        'routes': {
            'Patient': '/patient/dashboard',
            'Doctor': '/doctor/dashboard',
            'Admin': '/admin/dashboard'
        }
    }), 200