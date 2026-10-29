import os
from app import create_app
from app.config import Config

app = create_app()

if __name__ == '__main__':
    if Config.is_aws_mode():
        from app.models.dynamodb import db
        from app.services.sns import sns_service

        startup_errors = []
        if db.mode != 'aws':
            startup_errors.append(f"DynamoDB client initialization failed: {db.initialization_error or 'Boto3 is unavailable'}")
        if sns_service.mode != 'aws':
            startup_errors.append(f"SNS client initialization failed: {sns_service.initialization_error or 'Boto3 is unavailable'}")
        if startup_errors:
            raise RuntimeError('AWS_MODE requires working AWS clients. ' + ' '.join(startup_errors))

    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug_value = os.getenv('FLASK_DEBUG')
    debug = (
        debug_value.lower() in ('true', '1', 't')
        if debug_value is not None
        else bool(app.config.get('FLASK_DEBUG', False))
    )
    print("=" * 65)
    print("  MedTrack - Cloud-Based Healthcare Management System")
    print(f"  Running locally at: http://localhost:{port}")
    print(f"  Debug mode: {'enabled' if debug else 'disabled'}")
    print("=" * 65)
    app.run(host=host, port=port, debug=debug)
