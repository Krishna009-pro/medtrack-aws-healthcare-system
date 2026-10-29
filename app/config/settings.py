import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

    # Execution Mode: 'auto', 'local', or 'aws'
    AWS_MODE = os.getenv('AWS_MODE', 'auto').lower()

    # AWS Credentials and Configuration
    AWS_REGION = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION') or 'us-east-1'
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')
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
    SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
    SNS_APPOINTMENT_ALERTS_TOPIC = os.getenv('SNS_APPOINTMENT_ALERTS_TOPIC') or SNS_TOPIC_ARN
    SNS_DIAGNOSIS_UPDATES_TOPIC = os.getenv('SNS_DIAGNOSIS_UPDATES_TOPIC') or SNS_TOPIC_ARN

    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')

    @classmethod
    def has_aws_credentials(cls) -> bool:
        """Detect credentials through Boto3's full provider chain, including EC2 roles."""
        if cls.AWS_MODE == 'local':
            return False
        if cls.AWS_MODE == 'aws':
            return True
        try:
            import boto3
            return boto3.Session(region_name=cls.AWS_REGION).get_credentials() is not None
        except Exception:
            return False

    @classmethod
    def is_aws_mode(cls) -> bool:
        """
        Determines whether to execute in AWS Cloud Mode or Local Mock Mode.
        Automatically falls back to Local Mode if boto3 is not installed or the
        standard Boto3 credential chain cannot find credentials. On EC2 this
        chain can retrieve temporary credentials from the attached instance role.
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
