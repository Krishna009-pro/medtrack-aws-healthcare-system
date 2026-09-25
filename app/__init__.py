import os
from flask import Flask, jsonify, request, session
from app.config import config, Config
from app.blueprints.auth import auth_bp
from app.blueprints.patient import patient_bp
from app.blueprints.doctor import doctor_bp
from app.blueprints.admin import admin_bp
from app.blueprints.api import api_bp


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        mode_str = 'Local Mode' if not Config.is_aws_mode() else 'AWS Mode'
        return jsonify({
            'service': 'MedTrack',
            'message': 'Welcome to MedTrack API - Next-Generation Cloud Healthcare System',
            'status': 'online',
            'mode': mode_str,
            'version': '3.0.0',
            'endpoints': {
                'auth': '/auth',
                'patient': '/patient',
                'doctor': '/doctor',
                'admin': '/admin',
                'api': '/api',
                'health': '/health'
            }
        })

    @app.route('/dashboard')
    @app.route('/home')
    @app.route('/home1')
    def home():
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required', 'message': 'Please log in'}), 401

        role = session.get('role')
        if role == 'Patient':
            from app.blueprints.patient.routes import dashboard as p_dash
            return p_dash()
        elif role == 'Doctor':
            from app.blueprints.doctor.routes import dashboard as d_dash
            return d_dash()
        elif role == 'Admin':
            from app.blueprints.admin.routes import dashboard as a_dash
            return a_dash()
        return jsonify({'message': 'Authenticated', 'user_id': session.get('user_id'), 'role': role})

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            return jsonify({
                'message': 'Sign in to your MedTrack account',
                'method': 'POST',
                'endpoint': '/auth/login',
                'fields': ['email', 'password']
            })
        from app.blueprints.auth.routes import login as auth_login
        return auth_login()

    @app.route('/signup', methods=['GET', 'POST'])
    @app.route('/register', methods=['GET', 'POST'])
    def signup():
        if request.method == 'GET':
            return jsonify({
                'message': 'Create Account or Register for MedTrack',
                'method': 'POST',
                'endpoint': '/auth/register',
                'fields': ['email', 'name', 'password', 'confirm_password', 'role', 'phone']
            })
        from app.blueprints.auth.routes import register as auth_register
        return auth_register()

    @app.route('/logout')
    def logout():
        from app.blueprints.auth.routes import logout as auth_logout
        return auth_logout()

    @app.route('/about')
    def about():
        mode_str = 'Local Mode' if not Config.is_aws_mode() else 'AWS Mode'
        return jsonify({
            'service': 'MedTrack',
            'title': 'About MedTrack Architecture & Cloud Healthcare',
            'description': 'Decentralized-ready cloud healthcare operating system orchestrating patient queues, clinical electronic health records, and real-time telemetry.',
            'mode': mode_str,
            'stack': {
                'framework': 'Flask REST API',
                'database': 'Amazon DynamoDB (or Local JSON Partition)',
                'messaging': 'Amazon SNS',
                'cloud': 'AWS EC2 / IAM'
            }
        })

    @app.route('/contact_us')
    @app.route('/contact')
    def contact_us():
        return jsonify({
            'service': 'MedTrack',
            'title': 'Contact MedTrack 24/7 Support & Incident Escalation',
            'contact_email': 'support@medtrack.com',
            'escalation': 'Critical clinical and infrastructure dispatch'
        })

    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'medtrack',
            'mode': Config.get_mode(),
            'aws_enabled': Config.is_aws_mode(),
            'aws_region': Config.AWS_REGION
        })

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested endpoint does not exist on this MedTrack REST API.',
            'status_code': 404
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred on the server.',
            'status_code': 500
        }), 500

    return app