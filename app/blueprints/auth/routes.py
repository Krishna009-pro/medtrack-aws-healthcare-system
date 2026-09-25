from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import user_model, doctor_model, patient_model
from app.utils.auth import hash_password, verify_password

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'Patient')
        phone = request.form.get('phone', '').strip()

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
            return render_template('auth/register.html', errors=errors, form_data=request.form)

        password_hash = hash_password(password)
        user = user_model.create_user(email, name, password_hash, role, phone)

        if role == 'Doctor':
            specialization = request.form.get('specialization', '').strip()
            experience = request.form.get('experience', 0)
            try:
                experience = int(experience)
            except ValueError:
                experience = 0
            if specialization:
                doctor_model.create_doctor(user['UserID'], specialization, experience)
        elif role == 'Patient':
            age = request.form.get('age', 0)
            medical_history = request.form.get('medical_history', '').strip()
            try:
                age = int(age)
            except ValueError:
                age = 0
            patient_model.create_patient(user['UserID'], age, medical_history)

        flash('Registration successful! Please log in.', 'success')

        # SmartBridge Proof of Data Storage Server Log
        try:
            all_users = user_model.scan()
            formatted_users = [
                {
                    'id': u.get('UserID'),
                    'name': u.get('Name'),
                    'email': u.get('Email'),
                    'password': u.get('Password')
                }
                for u in all_users
            ]
            print("✅ Current Users List:", formatted_users)
        except Exception as e:
            print(f"Server Log Info: {e}")

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form_data={}, errors={})


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = user_model.get_by_email(email)
        if not user or not verify_password(password, user['Password']):
            flash('Invalid email or password', 'danger')
            return render_template('auth/login.html', email=email)

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

        # SmartBridge Proof of Data Storage Server Log
        print("👤 Logged In User Session:", session['user'])

        flash(f'Welcome back, {user["Name"]}!', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('auth.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@auth_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session and 'user' not in session:
        return redirect(url_for('auth.login'))

    if 'user' in session:
        print("👤 Current Session User Info:", session['user'])
    else:
        print("👤 Current Session User Info:", {
            'id': session.get('user_id'),
            'name': session.get('name'),
            'email': session.get('email'),
            'role': session.get('role')
        })

    role = session.get('role')
    if role == 'Patient':
        return redirect(url_for('patient.dashboard'))
    elif role == 'Doctor':
        return redirect(url_for('doctor.dashboard'))
    elif role == 'Admin':
        return redirect(url_for('admin.dashboard'))
    else:
        return redirect(url_for('auth.login'))