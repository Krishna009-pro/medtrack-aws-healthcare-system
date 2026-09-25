import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.config import Config

logger = logging.getLogger(__name__)

BOTO3_AVAILABLE = False
BotoKey = None
BotoAttr = None
ClientError = Exception

try:
    import boto3
    from boto3.dynamodb.conditions import Key as BotoKey, Attr as BotoAttr
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from app.models.local_storage import (
    LocalDynamoDBResource, LocalDynamoDBClientMock,
    KeyMock, AttrMock
)


def Key(name: str):
    """Dynamic factory returning Boto3 Key condition in AWS mode, or KeyMock in Local mode."""
    if Config.is_aws_mode() and BOTO3_AVAILABLE and BotoKey:
        return BotoKey(name)
    return KeyMock(name)


def Attr(name: str):
    """Dynamic factory returning Boto3 Attr condition in AWS mode, or AttrMock in Local mode."""
    if Config.is_aws_mode() and BOTO3_AVAILABLE and BotoAttr:
        return BotoAttr(name)
    return AttrMock(name)


class DynamoDBClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        if Config.is_aws_mode() and BOTO3_AVAILABLE:
            try:
                kwargs = {
                    'region_name': Config.AWS_REGION,
                    'aws_access_key_id': Config.AWS_ACCESS_KEY_ID,
                    'aws_secret_access_key': Config.AWS_SECRET_ACCESS_KEY
                }
                if Config.AWS_ENDPOINT_URL:
                    kwargs['endpoint_url'] = Config.AWS_ENDPOINT_URL

                self.dynamodb = boto3.resource('dynamodb', **kwargs)
                self.client = boto3.client('dynamodb', **kwargs)
                self.mode = 'aws'
                print(f"[MedTrack] Connected to AWS DynamoDB (Region: {Config.AWS_REGION})")
                return
            except Exception as e:
                print(f"[MedTrack] Warning: Failed to connect to AWS DynamoDB ({e}). Falling back to Local Mode.")

        self.mode = 'local'
        self.dynamodb = LocalDynamoDBResource()
        self.client = LocalDynamoDBClientMock()
        print("[MedTrack] Running in LOCAL MODE (Local Mock Storage). Set valid AWS credentials to automatically switch to AWS.")

    def get_table(self, table_name: str):
        return self.dynamodb.Table(table_name)


db = DynamoDBClient()


class BaseModel:
    table_name = None
    pk_field = 'PK'
    sk_field = 'SK'

    def __init__(self):
        self.table = db.get_table(self.table_name)

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _timestamp(self) -> str:
        return datetime.utcnow().isoformat()

    def save(self, item: Dict[str, Any]) -> Dict[str, Any]:
        self.table.put_item(Item=item)
        return item

    def get_by_id(self, pk_value: str, sk_value: str = None) -> Optional[Dict[str, Any]]:
        key = {self.pk_field: pk_value}
        if sk_value:
            key[self.sk_field] = sk_value
        response = self.table.get_item(Key=key)
        return response.get('Item')

    def query(self, pk_value: str, sk_condition=None, index_name: str = None, **kwargs) -> List[Dict[str, Any]]:
        key_condition = Key(self.pk_field).eq(pk_value)
        if sk_condition:
            key_condition &= sk_condition

        query_params = {'KeyConditionExpression': key_condition}
        if index_name:
            query_params['IndexName'] = index_name

        query_params.update(kwargs)
        response = self.table.query(**query_params)
        return response.get('Items', [])

    def scan(self, filter_expression=None, **kwargs) -> List[Dict[str, Any]]:
        scan_params = {}
        if filter_expression:
            scan_params['FilterExpression'] = filter_expression
        scan_params.update(kwargs)
        response = self.table.scan(**scan_params)
        return response.get('Items', [])

    def update(self, pk_value: str, sk_value: str, update_expression: str, expression_values: Dict, expression_names: Dict = None) -> Dict[str, Any]:
        key = {self.pk_field: pk_value}
        if sk_value:
            key[self.sk_field] = sk_value

        update_params = {
            'Key': key,
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values,
            'ReturnValues': 'ALL_NEW'
        }
        if expression_names:
            update_params['ExpressionAttributeNames'] = expression_names

        response = self.table.update_item(**update_params)
        return response.get('Attributes', {})

    def delete(self, pk_value: str, sk_value: str = None) -> bool:
        key = {self.pk_field: pk_value}
        if sk_value:
            key[self.sk_field] = sk_value
        self.table.delete_item(Key=key)
        return True


class UserModel(BaseModel):
    table_name = Config.DYNAMODB_USERS_TABLE
    pk_field = 'UserID'
    sk_field = 'UserID'

    def create_user(self, email: str, name: str, password_hash: str, role: str, phone: str = '') -> Dict[str, Any]:
        user_id = self._generate_id()
        item = {
            'UserID': user_id,
            'Email': email.lower(),
            'Name': name,
            'Password': password_hash,
            'Role': role,
            'Phone': phone,
            'CreatedAt': self._timestamp(),
            'UpdatedAt': self._timestamp()
        }
        return self.save(item)

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            IndexName='EmailIndex',
            KeyConditionExpression=Key('Email').eq(email.lower())
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return super().get_by_id(user_id, user_id)

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        update_expr = 'SET '
        expr_values = {}
        expr_names = {}
        for i, (key, value) in enumerate(updates.items()):
            if key not in ['UserID', 'Email', 'Password', 'CreatedAt']:
                attr_name = f'#attr{i}'
                attr_value = f':val{i}'
                update_expr += f'{attr_name} = {attr_value}, '
                expr_names[attr_name] = key
                expr_values[attr_value] = value
        update_expr = update_expr.rstrip(', ')
        update_expr += ', #updated = :updated'
        expr_names['#updated'] = 'UpdatedAt'
        expr_values[':updated'] = self._timestamp()

        return self.update(user_id, user_id, update_expr, expr_values, expr_names)


class DoctorModel(BaseModel):
    table_name = Config.DYNAMODB_DOCTORS_TABLE
    pk_field = 'DoctorID'
    sk_field = 'DoctorID'

    def create_doctor(self, user_id: str, specialization: str, experience: int) -> Dict[str, Any]:
        doctor_id = self._generate_id()
        item = {
            'DoctorID': doctor_id,
            'UserID': user_id,
            'Specialization': specialization,
            'Experience': experience,
            'CreatedAt': self._timestamp(),
            'UpdatedAt': self._timestamp()
        }
        return self.save(item)

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            IndexName='UserIDIndex',
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def get_by_id(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        return super().get_by_id(doctor_id, doctor_id)

    def get_all_doctors(self) -> List[Dict[str, Any]]:
        return self.scan()

    def get_by_specialization(self, specialization: str) -> List[Dict[str, Any]]:
        return self.scan(FilterExpression=Attr('Specialization').eq(specialization))


class PatientModel(BaseModel):
    table_name = Config.DYNAMODB_PATIENTS_TABLE
    pk_field = 'PatientID'
    sk_field = 'PatientID'

    def create_patient(self, user_id: str, age: int, medical_history: str = '') -> Dict[str, Any]:
        patient_id = self._generate_id()
        item = {
            'PatientID': patient_id,
            'UserID': user_id,
            'Age': age,
            'MedicalHistory': medical_history,
            'CreatedAt': self._timestamp(),
            'UpdatedAt': self._timestamp()
        }
        return self.save(item)

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            IndexName='UserIDIndex',
            KeyConditionExpression=Key('UserID').eq(user_id)
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def get_by_id(self, patient_id: str) -> Optional[Dict[str, Any]]:
        return super().get_by_id(patient_id, patient_id)

    def update_medical_history(self, patient_id: str, medical_history: str) -> Dict[str, Any]:
        return self.update(
            patient_id, patient_id,
            'SET MedicalHistory = :mh, UpdatedAt = :ua',
            {':mh': medical_history, ':ua': self._timestamp()}
        )


class AppointmentModel(BaseModel):
    table_name = Config.DYNAMODB_APPOINTMENTS_TABLE
    pk_field = 'AppointmentID'
    sk_field = 'AppointmentID'

    def create_appointment(self, patient_id: str, doctor_id: str, date: str, time: str) -> Dict[str, Any]:
        appointment_id = self._generate_id()
        item = {
            'AppointmentID': appointment_id,
            'PatientID': patient_id,
            'DoctorID': doctor_id,
            'Date': date,
            'Time': time,
            'Status': 'Pending',
            'CreatedAt': self._timestamp(),
            'UpdatedAt': self._timestamp()
        }
        return self.save(item)

    def get_by_id(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        return super().get_by_id(appointment_id, appointment_id)

    def get_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        return self.query(
            patient_id,
            index_name='PatientIDIndex',
            KeyConditionExpression=Key('PatientID').eq(patient_id)
        )

    def get_by_doctor(self, doctor_id: str) -> List[Dict[str, Any]]:
        return self.query(
            doctor_id,
            index_name='DoctorIDIndex',
            KeyConditionExpression=Key('DoctorID').eq(doctor_id)
        )

    def get_by_doctor_date(self, doctor_id: str, date: str) -> List[Dict[str, Any]]:
        response = self.table.query(
            IndexName='DoctorIDIndex',
            KeyConditionExpression=Key('DoctorID').eq(doctor_id),
            FilterExpression=Attr('Date').eq(date)
        )
        return response.get('Items', [])

    def update_status(self, appointment_id: str, status: str) -> Dict[str, Any]:
        return self.update(
            appointment_id, appointment_id,
            'SET #status = :status, UpdatedAt = :ua',
            {':status': status, ':ua': self._timestamp()},
            {'#status': 'Status'}
        )

    def check_slot_available(self, doctor_id: str, date: str, time: str) -> bool:
        appointments = self.get_by_doctor_date(doctor_id, date)
        for apt in appointments:
            if apt.get('Time') == time and apt.get('Status') in ['Pending', 'Confirmed']:
                return False
        return True


class DiagnosisModel(BaseModel):
    table_name = Config.DYNAMODB_DIAGNOSIS_TABLE
    pk_field = 'DiagnosisID'
    sk_field = 'DiagnosisID'

    def create_diagnosis(self, appointment_id: str, doctor_id: str, patient_id: str, report: str) -> Dict[str, Any]:
        diagnosis_id = self._generate_id()
        item = {
            'DiagnosisID': diagnosis_id,
            'AppointmentID': appointment_id,
            'DoctorID': doctor_id,
            'PatientID': patient_id,
            'Report': report,
            'Date': datetime.utcnow().strftime('%Y-%m-%d'),
            'CreatedAt': self._timestamp(),
            'UpdatedAt': self._timestamp()
        }
        return self.save(item)

    def get_by_id(self, diagnosis_id: str) -> Optional[Dict[str, Any]]:
        return super().get_by_id(diagnosis_id, diagnosis_id)

    def get_by_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            IndexName='AppointmentIDIndex',
            KeyConditionExpression=Key('AppointmentID').eq(appointment_id)
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def get_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        return self.query(
            patient_id,
            index_name='PatientIDIndex',
            KeyConditionExpression=Key('PatientID').eq(patient_id)
        )

    def get_by_doctor(self, doctor_id: str) -> List[Dict[str, Any]]:
        return self.query(
            doctor_id,
            index_name='DoctorIDIndex',
            KeyConditionExpression=Key('DoctorID').eq(doctor_id)
        )


class NotificationModel(BaseModel):
    table_name = Config.DYNAMODB_NOTIFICATIONS_TABLE
    pk_field = 'NotificationID'
    sk_field = 'NotificationID'

    def create_notification(self, user_id: str, message: str) -> Dict[str, Any]:
        notification_id = self._generate_id()
        item = {
            'NotificationID': notification_id,
            'UserID': user_id,
            'Message': message,
            'Timestamp': self._timestamp(),
            'Read': False
        }
        return self.save(item)

    def get_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.query(
            user_id,
            index_name='UserIDIndex',
            KeyConditionExpression=Key('UserID').eq(user_id),
            Limit=limit,
            ScanIndexForward=False
        )

    def mark_as_read(self, notification_id: str) -> Dict[str, Any]:
        return self.update(
            notification_id, notification_id,
            'SET #read = :read',
            {':read': True},
            {'#read': 'Read'}
        )


user_model = UserModel()
doctor_model = DoctorModel()
patient_model = PatientModel()
appointment_model = AppointmentModel()
diagnosis_model = DiagnosisModel()
notification_model = NotificationModel()