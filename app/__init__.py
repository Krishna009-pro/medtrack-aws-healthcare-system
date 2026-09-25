from flask import Flask
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
        import os
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
        app_mode=Config.get_mode()
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        from flask import redirect, url_for, session
        if 'user_id' in session:
            return redirect(url_for('auth.dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/health')
    def health():
        return {
            'status': 'healthy',
            'service': 'medtrack',
            'mode': Config.get_mode(),
            'aws_enabled': Config.is_aws_mode(),
            'aws_region': Config.AWS_REGION
        }

    @app.errorhandler(404)
    def not_found(error):
        from flask import render_template
        return render_template('base/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        return render_template('base/500.html'), 500

    return app