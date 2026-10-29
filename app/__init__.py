import os
from flask import Flask, render_template, redirect, url_for, session, request
from app.config import config, Config
from app.blueprints.auth import auth_bp
from app.blueprints.patient import patient_bp
from app.blueprints.doctor import doctor_bp
from app.blueprints.admin import admin_bp
from app.blueprints.api import api_bp
from app.models import (
    user_model, doctor_model, patient_model,
    appointment_model, diagnosis_model, notification_model
)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Register helper functions, models, and operational mode into Jinja environment
    app.jinja_env.globals.update(
        format_date=lambda d: __import__('app.utils.helpers', fromlist=['format_date']).format_date(d),
        format_time=lambda t: __import__('app.utils.helpers', fromlist=['format_time']).format_time(t),
        user_model=user_model,
        doctor_model=doctor_model,
        patient_model=patient_model,
        appointment_model=appointment_model,
        diagnosis_model=diagnosis_model,
        notification_model=notification_model,
        app_mode='AWS Mode' if Config.is_aws_mode() else 'Local Mode'
    )

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        if 'user_id' in session or 'user' in session:
            return redirect(url_for('home'))
        return render_template('index.html')

    @app.route('/dashboard')
    @app.route('/home')
    @app.route('/home1')
    def home():
        if 'user_id' not in session and 'user' not in session:
            return redirect(url_for('login'))

        role = session.get('role')
        if role == 'Patient':
            return redirect(url_for('patient.dashboard'))
        elif role == 'Doctor':
            return redirect(url_for('doctor.dashboard'))
        elif role == 'Admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        from app.blueprints.auth.routes import login as auth_login
        return auth_login()

    @app.route('/signup', methods=['GET', 'POST'])
    @app.route('/register', methods=['GET', 'POST'])
    def signup():
        from app.blueprints.auth.routes import register as auth_register
        return auth_register()

    @app.route('/logout')
    def logout():
        from app.blueprints.auth.routes import logout as auth_logout
        return auth_logout()

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact_us')
    @app.route('/contact')
    def contact_us():
        return render_template('contact_us.html')

    @app.route('/health')
    def health():
        return {
            'status': 'healthy',
            'service': 'medtrack',
            'mode': Config.get_mode(),
            'aws_enabled': Config.is_aws_mode(),
            'database_backend': getattr(__import__('app.models.dynamodb', fromlist=['db']).db, 'mode', 'unknown'),
            'aws_region': Config.AWS_REGION
        }

    @app.errorhandler(404)
    def not_found(error):
        return render_template('base/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('base/500.html'), 500

    return app
