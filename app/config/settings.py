import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    # Execution Mode: 'auto', 'local', or 'aws'
    AWS_MODE = os.getenv('AWS_MODE', 'auto').lower()

    # AWS Credentials and Configuration
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_ENDPOINT_URL = os.getenv('AWS_ENDPOINT_URL')
    SNS_ENDPOINT_URL = os.getenv('SNS_ENDPOINT_URL')

    # Data directory for persistent local storage in Local Mode
    DATA_DIR = os.getenv(
        'DATA_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
    )

    # DynamoDB Tables
    DYNAMODB_USERS_TABLE = os.getenv('DYNAMODB_USERS_TABLE', 'medtrack-users')
    DYNAMODB_DOCTORS_TABLE = os.getenv('DYNAMODB_DOCTORS_TABLE', 'medtrack-doctors')
    DYNAMODB_PATIENTS_TABLE = os.getenv('DYNAMODB_PATIENTS_TABLE', 'medtrack-patients')
    DYNAMODB_APPOINTMENTS_TABLE = os.getenv('DYNAMODB_APPOINTMENTS_TABLE', 'medtrack-appointments')
    DYNAMODB_DIAGNOSIS_TABLE = os.getenv('DYNAMODB_DIAGNOSIS_TABLE', 'medtrack-diagnosis')
    DYNAMODB_NOTIFICATIONS_TABLE = os.getenv('DYNAMODB_NOTIFICATIONS_TABLE', 'medtrack-notifications')

    # SNS Topics
    SNS_APPOINTMENT_ALERTS_TOPIC = os.getenv('SNS_APPOINTMENT_ALERTS_TOPIC')
    SNS_DIAGNOSIS_UPDATES_TOPIC = os.getenv('SNS_DIAGNOSIS_UPDATES_TOPIC')

    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')

    @classmethod
    def has_aws_credentials(cls) -> bool:
        """Check if valid AWS credentials or instance metadata credentials are present."""
        if cls.AWS_MODE == 'local':
            return False

        key = (os.getenv('AWS_ACCESS_KEY_ID') or '').strip()
        secret = (os.getenv('AWS_SECRET_ACCESS_KEY') or '').strip()

        # Reject common placeholder strings from .env templates
        placeholders = {
            'your-access-key', 'your-secret-key', 'your-access-key-id',
            'your-secret-access-key', 'test', 'none', 'placeholder', 'xxx', ''
        }
        if key and secret and (key.lower() not in placeholders) and (secret.lower() not in placeholders):
            return True

        # Check for EC2 instance profile / ECS IAM role environment variables
        if os.getenv('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI') or os.getenv('AWS_EXECUTION_ENV'):
            return True

        return False

    @classmethod
    def is_aws_mode(cls) -> bool:
        """
        Determines whether to execute in AWS Cloud Mode or Local Mock Mode.
        Automatically falls back to Local Mode if boto3 is not installed or credentials are absent.
        """
        if cls.AWS_MODE == 'local':
            return False
        if cls.AWS_MODE == 'aws':
            return True

        # Mode is 'auto': check boto3 library availability and credentials
        try:
            import boto3  # noqa: F401
            return cls.has_aws_credentials()
        except ImportError:
            return False

    @classmethod
    def get_mode(cls) -> str:
        """Returns the current operational mode: 'aws' or 'local'."""
        return 'aws' if cls.is_aws_mode() else 'local'


class DevelopmentConfig(Config):
    FLASK_DEBUG = True


class ProductionConfig(Config):
    FLASK_DEBUG = False


class TestingConfig(Config):
    TESTING = True
    FLASK_DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}