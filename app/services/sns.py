import os
import uuid
import logging
from datetime import datetime
from typing import Dict, Any
from app.config import Config

logger = logging.getLogger(__name__)

BOTO3_AVAILABLE = False
ClientError = Exception

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None
    BOTO3_AVAILABLE = False


class LocalSNSClientMock:
    """Local mock client simulating AWS SNS."""
    def __init__(self):
        self.data_dir = getattr(Config, 'DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data'))
        self.log_file = os.path.join(self.data_dir, 'sns_notifications.log')
        os.makedirs(self.data_dir, exist_ok=True)

    def publish(self, TopicArn: str, Message: str, Subject: str = None) -> Dict[str, Any]:
        msg_id = f"local-msg-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.utcnow().isoformat()
        log_entry = (
            f"[{timestamp}] [LOCAL SNS MOCK DISPATCH]\n"
            f"MessageId: {msg_id}\n"
            f"TopicArn:  {TopicArn}\n"
            f"Subject:   {Subject or 'No Subject'}\n"
            f"Message:\n{Message.strip()}\n"
            f"{'-'*60}\n"
        )
        print(f"\n[MedTrack Local SNS] Notification dispatched (ID: {msg_id})")
        print(f"Subject: {Subject or 'No Subject'}")
        print(f"Topic:   {TopicArn}")
        print(f"Message: {Message.strip()[:120]}...\n")

        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            logger.warning(f"Could not write to SNS log: {e}")

        return {'MessageId': msg_id, 'ResponseMetadata': {'HTTPStatusCode': 200}}


class SNSService:
    _instance = None
    initialization_error = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        self.initialization_error = None
        if Config.is_aws_mode() and BOTO3_AVAILABLE:
            try:
                # Let Boto3 obtain temporary EC2 role credentials when static
                # access keys are not configured.
                kwargs = {'region_name': Config.AWS_REGION}
                if Config.AWS_ACCESS_KEY_ID and Config.AWS_SECRET_ACCESS_KEY:
                    kwargs['aws_access_key_id'] = Config.AWS_ACCESS_KEY_ID
                    kwargs['aws_secret_access_key'] = Config.AWS_SECRET_ACCESS_KEY
                    if Config.AWS_SESSION_TOKEN:
                        kwargs['aws_session_token'] = Config.AWS_SESSION_TOKEN
                if Config.SNS_ENDPOINT_URL:
                    kwargs['endpoint_url'] = Config.SNS_ENDPOINT_URL

                self.sns = boto3.client('sns', **kwargs)
                self.mode = 'aws'
                print(f"[MedTrack] Connected to AWS SNS (Region: {Config.AWS_REGION})")
                return
            except Exception as e:
                self.initialization_error = e
                print(f"[MedTrack] Warning: Failed to connect to AWS SNS ({e}). Falling back to Local Mode.")

        self.mode = 'local'
        self.sns = LocalSNSClientMock()
        print("[MedTrack] SNS Service running in LOCAL MODE (Dispatched notifications saved to data/sns_notifications.log). To publish to AWS, attach an EC2 instance role or configure another Boto3 credential provider.")

    def publish(self, topic_arn: str, message: str, subject: str = None) -> Dict[str, Any]:
        if self.mode == 'local':
            effective_topic = topic_arn or 'arn:aws:sns:local:mock:MedTrack-Alerts'
            res = self.sns.publish(TopicArn=effective_topic, Message=message, Subject=subject)
            return {'success': True, 'message_id': res.get('MessageId'), 'mode': 'local'}

        try:
            params = {'TopicArn': topic_arn, 'Message': message}
            if subject:
                params['Subject'] = subject
            response = self.sns.publish(**params)
            return {'success': True, 'message_id': response.get('MessageId'), 'mode': 'aws'}
        except ClientError as e:
            return {'success': False, 'error': str(e), 'mode': 'aws'}

    def send_appointment_notification(self, user_email: str, user_phone: str, appointment_details: Dict, notification_type: str) -> Dict[str, Any]:
        topic_arn = Config.SNS_APPOINTMENT_ALERTS_TOPIC
        if not topic_arn and self.mode != 'local':
            return {'success': False, 'error': 'SNS topic not configured'}

        if notification_type == 'booking':
            subject = 'Appointment Booked - MedTrack'
            message = f"""
Dear Patient,

Your appointment has been successfully booked!

Details:
- Doctor: {appointment_details.get('doctor_name', 'N/A')}
- Date: {appointment_details.get('date', 'N/A')}
- Time: {appointment_details.get('time', 'N/A')}
- Status: {appointment_details.get('status', 'Pending')}

Please arrive 10 minutes before your scheduled time.

Thank you for using MedTrack!
"""
        elif notification_type == 'confirmation':
            subject = 'Appointment Confirmed - MedTrack'
            message = f"""
Dear Patient,

Your appointment has been confirmed!

Details:
- Doctor: {appointment_details.get('doctor_name', 'N/A')}
- Date: {appointment_details.get('date', 'N/A')}
- Time: {appointment_details.get('time', 'N/A')}

We look forward to seeing you.

Thank you for using MedTrack!
"""
        elif notification_type == 'cancellation':
            subject = 'Appointment Cancelled - MedTrack'
            message = f"""
Dear Patient,

Your appointment has been cancelled.

Details:
- Doctor: {appointment_details.get('doctor_name', 'N/A')}
- Date: {appointment_details.get('date', 'N/A')}
- Time: {appointment_details.get('time', 'N/A')}

If you wish to reschedule, please log in to your MedTrack account.

Thank you for using MedTrack!
"""
        elif notification_type == 'reminder':
            subject = 'Appointment Reminder - MedTrack'
            message = f"""
Dear Patient,

This is a reminder for your upcoming appointment.

Details:
- Doctor: {appointment_details.get('doctor_name', 'N/A')}
- Date: {appointment_details.get('date', 'N/A')}
- Time: {appointment_details.get('time', 'N/A')}

Please arrive 10 minutes before your scheduled time.

Thank you for using MedTrack!
"""
        else:
            return {'success': False, 'error': 'Invalid notification type'}

        return self.publish(topic_arn, message, subject)

    def send_diagnosis_notification(self, user_email: str, user_phone: str, diagnosis_details: Dict) -> Dict[str, Any]:
        topic_arn = Config.SNS_DIAGNOSIS_UPDATES_TOPIC
        if not topic_arn and self.mode != 'local':
            return {'success': False, 'error': 'SNS topic not configured'}

        subject = 'New Diagnosis Report Available - MedTrack'
        message = f"""
Dear Patient,

A new diagnosis report is available for your review.

Details:
- Doctor: {diagnosis_details.get('doctor_name', 'N/A')}
- Date: {diagnosis_details.get('date', 'N/A')}
- Appointment: {diagnosis_details.get('appointment_date', 'N/A')}

Please log in to your MedTrack account to view the full report.

Thank you for using MedTrack!
"""
        return self.publish(topic_arn, message, subject)

    def send_doctor_notification(self, doctor_email: str, doctor_phone: str, message: str, subject: str) -> Dict[str, Any]:
        topic_arn = Config.SNS_APPOINTMENT_ALERTS_TOPIC
        if not topic_arn and self.mode != 'local':
            return {'success': False, 'error': 'SNS topic not configured'}
        return self.publish(topic_arn, message, subject)


sns_service = SNSService()
