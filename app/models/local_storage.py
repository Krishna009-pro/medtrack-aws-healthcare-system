"""
Local Storage & Mock Engine for AWS DynamoDB
Provides offline, in-memory, and JSON-backed persistence when AWS credentials are not available.
Automatically switches to AWS DynamoDB when valid credentials are provided.
"""

import os
import json
import uuid
import copy
import re
import threading
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from werkzeug.security import generate_password_hash
from app.config import Config


logger = logging.getLogger(__name__)


class ConditionMock:
    """Simulates Boto3 DynamoDB Key/Attr condition expressions."""
    def __init__(self, attribute: str, operator: str, value: Any):
        self.attribute = attribute
        self.operator = operator
        self.value = value

    def __and__(self, other):
        return CompoundConditionMock(self, other, 'AND')

    def __or__(self, other):
        return CompoundConditionMock(self, other, 'OR')

    def evaluate(self, item: Dict[str, Any]) -> bool:
        item_val = item.get(self.attribute)
        if self.operator == 'eq':
            if isinstance(item_val, str) and isinstance(self.value, str):
                if self.attribute.lower() == 'email':
                    return item_val.lower() == self.value.lower()
                return item_val == self.value
            return item_val == self.value
        elif self.operator == 'ne':
            return item_val != self.value
        elif self.operator == 'gt':
            return (item_val or 0) > self.value
        elif self.operator == 'gte':
            return (item_val or 0) >= self.value
        elif self.operator == 'lt':
            return (item_val or 0) < self.value
        elif self.operator == 'lte':
            return (item_val or 0) <= self.value
        elif self.operator == 'begins_with':
            return str(item_val or '').startswith(str(self.value))
        return False


class CompoundConditionMock:
    """Simulates composite conditions (AND/OR)."""
    def __init__(self, left, right, op='AND'):
        self.left = left
        self.right = right
        self.op = op

    def __and__(self, other):
        return CompoundConditionMock(self, other, 'AND')

    def evaluate(self, item: Dict[str, Any]) -> bool:
        if self.op == 'AND':
            return self.left.evaluate(item) and self.right.evaluate(item)
        elif self.op == 'OR':
            return self.left.evaluate(item) or self.right.evaluate(item)
        return False


class KeyMock:
    """Mock for boto3.dynamodb.conditions.Key."""
    def __init__(self, name: str):
        self.name = name

    def eq(self, value: Any):
        return ConditionMock(self.name, 'eq', value)

    def begins_with(self, value: Any):
        return ConditionMock(self.name, 'begins_with', value)


class AttrMock:
    """Mock for boto3.dynamodb.conditions.Attr."""
    def __init__(self, name: str):
        self.name = name

    def eq(self, value: Any):
        return ConditionMock(self.name, 'eq', value)

    def ne(self, value: Any):
        return ConditionMock(self.name, 'ne', value)

    def gt(self, value: Any):
        return ConditionMock(self.name, 'gt', value)

    def gte(self, value: Any):
        return ConditionMock(self.name, 'gte', value)

    def lt(self, value: Any):
        return ConditionMock(self.name, 'lt', value)

    def lte(self, value: Any):
        return ConditionMock(self.name, 'lte', value)


class LocalStorageManager:
    """Singleton managing persistent JSON storage for mock DynamoDB tables."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_storage()
        return cls._instance

    def _init_storage(self):
        self.data_dir = getattr(Config, 'DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data'))
        self.db_file = os.path.join(self.data_dir, 'local_db.json')
        os.makedirs(self.data_dir, exist_ok=True)
        self.tables = {}
        self._load()

    def _load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.tables = json.load(f)
                return
            except Exception as e:
                logger.warning(f"Error loading local database ({e}). Creating new database with seed data.")

        # Initialize with default seed data
        self.tables = self._generate_seed_data()
        self._save()

    def _save(self):
        try:
            temp_file = f"{self.db_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.tables, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.db_file):
                os.replace(temp_file, self.db_file)
            else:
                os.rename(temp_file, self.db_file)
        except Exception as e:
            logger.error(f"Failed to persist local database: {e}")

    def get_table_data(self, table_name: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if table_name not in self.tables:
                self.tables[table_name] = {}
            return self.tables[table_name]

    def save_item(self, table_name: str, item_id: str, item: Dict[str, Any]):
        with self._lock:
            if table_name not in self.tables:
                self.tables[table_name] = {}
            self.tables[table_name][item_id] = copy.deepcopy(item)
            self._save()

    def delete_item(self, table_name: str, item_id: str):
        with self._lock:
            if table_name in self.tables and item_id in self.tables[table_name]:
                del self.tables[table_name][item_id]
                self._save()

    def _generate_seed_data(self) -> Dict[str, Dict[str, Any]]:
        """Pre-populate sample Admin, Doctors, Patients, and Appointments for immediate local testing."""
        now = datetime.utcnow().isoformat()
        today = datetime.utcnow().strftime('%Y-%m-%d')

        users = {
            'admin-user-001': {
                'UserID': 'admin-user-001',
                'Name': 'System Administrator',
                'Email': 'admin@medtrack.com',
                'Password': generate_password_hash('Admin@12345'),
                'Role': 'Admin',
                'Phone': '+1-555-0100',
                'CreatedAt': now,
                'UpdatedAt': now
            },
            'doc-user-001': {
                'UserID': 'doc-user-001',
                'Name': 'Dr. Sarah Jenkins',
                'Email': 'doctor@medtrack.com',
                'Password': generate_password_hash('Doctor@12345'),
                'Role': 'Doctor',
                'Phone': '+1-555-0101',
                'CreatedAt': now,
                'UpdatedAt': now
            },
            'doc-user-002': {
                'UserID': 'doc-user-002',
                'Name': 'Dr. Michael Chen',
                'Email': 'dr.chen@medtrack.com',
                'Password': generate_password_hash('Doctor@12345'),
                'Role': 'Doctor',
                'Phone': '+1-555-0102',
                'CreatedAt': now,
                'UpdatedAt': now
            },
            'pat-user-001': {
                'UserID': 'pat-user-001',
                'Name': 'Jane Doe',
                'Email': 'patient@medtrack.com',
                'Password': generate_password_hash('Patient@12345'),
                'Role': 'Patient',
                'Phone': '+1-555-0103',
                'CreatedAt': now,
                'UpdatedAt': now
            }
        }

        doctors = {
            'doc-001': {
                'DoctorID': 'doc-001',
                'UserID': 'doc-user-001',
                'Specialization': 'Cardiology',
                'Experience': 12,
                'CreatedAt': now,
                'UpdatedAt': now
            },
            'doc-002': {
                'DoctorID': 'doc-002',
                'UserID': 'doc-user-002',
                'Specialization': 'General Practice',
                'Experience': 8,
                'CreatedAt': now,
                'UpdatedAt': now
            }
        }

        patients = {
            'pat-001': {
                'PatientID': 'pat-001',
                'UserID': 'pat-user-001',
                'Age': 34,
                'MedicalHistory': 'Asthma diagnosed in 2018. Penicillin allergy. Prior appendectomy (2020).',
                'CreatedAt': now,
                'UpdatedAt': now
            }
        }

        appointments = {
            'apt-001': {
                'AppointmentID': 'apt-001',
                'PatientID': 'pat-001',
                'DoctorID': 'doc-001',
                'Date': today,
                'Time': '10:00',
                'Status': 'Confirmed',
                'CreatedAt': now,
                'UpdatedAt': now
            }
        }

        diagnosis = {
            'diag-001': {
                'DiagnosisID': 'diag-001',
                'AppointmentID': 'apt-001',
                'DoctorID': 'doc-001',
                'PatientID': 'pat-001',
                'Report': 'Annual cardiovascular assessment: Blood pressure 118/76 mmHg. Resting pulse 72 bpm. EKG demonstrates regular sinus rhythm. Continue balanced diet and light cardio exercise.',
                'Date': today,
                'CreatedAt': now,
                'UpdatedAt': now
            }
        }

        notifications = {
            'notif-001': {
                'NotificationID': 'notif-001',
                'UserID': 'pat-user-001',
                'Message': f'Welcome to MedTrack! Your consultation with Dr. Sarah Jenkins is confirmed for {today} at 10:00 AM.',
                'Timestamp': now,
                'Read': False
            },
            'notif-002': {
                'NotificationID': 'notif-002',
                'UserID': 'doc-user-001',
                'Message': f'Confirmed appointment with patient Jane Doe scheduled for {today} at 10:00 AM.',
                'Timestamp': now,
                'Read': False
            }
        }

        return {
            Config.DYNAMODB_USERS_TABLE: users,
            Config.DYNAMODB_DOCTORS_TABLE: doctors,
            Config.DYNAMODB_PATIENTS_TABLE: patients,
            Config.DYNAMODB_APPOINTMENTS_TABLE: appointments,
            Config.DYNAMODB_DIAGNOSIS_TABLE: diagnosis,
            Config.DYNAMODB_NOTIFICATIONS_TABLE: notifications
        }


class LocalDynamoDBTable:
    """
    Simulates a boto3 DynamoDB Table instance.
    Implements put_item, get_item, query, scan, update_item, and delete_item.
    """
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.storage = LocalStorageManager()

    def _get_item_key(self, item: Dict[str, Any]) -> str:
        for key in ['UserID', 'DoctorID', 'PatientID', 'AppointmentID', 'DiagnosisID', 'NotificationID', 'PK']:
            if key in item:
                return str(item[key])
        return str(item.get('id', uuid.uuid4()))

    def put_item(self, Item: Dict[str, Any]) -> Dict[str, Any]:
        item_id = self._get_item_key(Item)
        self.storage.save_item(self.table_name, item_id, Item)
        return {'ResponseMetadata': {'HTTPStatusCode': 200}}

    def get_item(self, Key: Dict[str, Any]) -> Dict[str, Any]:
        table_data = self.storage.get_table_data(self.table_name)
        # Direct lookup if primary key provided
        for pk_val in Key.values():
            if str(pk_val) in table_data:
                item = table_data[str(pk_val)]
                # Verify all keys match
                if all(item.get(k) == v for k, v in Key.items()):
                    return {'Item': copy.deepcopy(item)}

        # Search across all items
        for item in table_data.values():
            if all(item.get(k) == v for k, v in Key.items()):
                return {'Item': copy.deepcopy(item)}

        return {}

    def query(self, KeyConditionExpression=None, IndexName=None, FilterExpression=None, Limit=None, ScanIndexForward=True, **kwargs) -> Dict[str, Any]:
        table_data = self.storage.get_table_data(self.table_name)
        items = list(table_data.values())

        # Evaluate KeyConditionExpression
        if KeyConditionExpression is not None:
            if hasattr(KeyConditionExpression, 'evaluate'):
                items = [it for it in items if KeyConditionExpression.evaluate(it)]
            elif isinstance(KeyConditionExpression, dict):
                items = [it for it in items if all(it.get(k) == v for k, v in KeyConditionExpression.items())]

        # Evaluate FilterExpression
        if FilterExpression is not None:
            if hasattr(FilterExpression, 'evaluate'):
                items = [it for it in items if FilterExpression.evaluate(it)]
            elif isinstance(FilterExpression, dict):
                items = [it for it in items if all(it.get(k) == v for k, v in FilterExpression.items())]

        # Sort order (e.g. for notifications reverse chronologically)
        if ScanIndexForward is False:
            items.reverse()

        if Limit is not None:
            items = items[:int(Limit)]

        return {'Items': copy.deepcopy(items)}

    def scan(self, FilterExpression=None, **kwargs) -> Dict[str, Any]:
        table_data = self.storage.get_table_data(self.table_name)
        items = list(table_data.values())

        if FilterExpression is not None:
            if hasattr(FilterExpression, 'evaluate'):
                items = [it for it in items if FilterExpression.evaluate(it)]
            elif isinstance(FilterExpression, dict):
                items = [it for it in items if all(it.get(k) == v for k, v in FilterExpression.items())]

        return {'Items': copy.deepcopy(items)}

    def update_item(self, Key: Dict[str, Any], UpdateExpression: str, ExpressionAttributeValues: Dict, ExpressionAttributeNames: Dict = None, ReturnValues='ALL_NEW') -> Dict[str, Any]:
        table_data = self.storage.get_table_data(self.table_name)
        target_item = None
        target_id = None

        # Locate item
        for pk_val in Key.values():
            if str(pk_val) in table_data:
                target_id = str(pk_val)
                target_item = table_data[target_id]
                break

        if not target_item:
            for item_id, it in table_data.items():
                if all(it.get(k) == v for k, v in Key.items()):
                    target_id = item_id
                    target_item = it
                    break

        if not target_item:
            return {'Attributes': {}}

        # Parse DynamoDB SET expression
        expr_names = ExpressionAttributeNames or {}
        expr_vals = ExpressionAttributeValues or {}

        # Remove SET keyword
        clean_expr = re.sub(r'^\s*SET\s+', '', UpdateExpression, flags=re.IGNORECASE)
        clauses = [c.strip() for c in clean_expr.split(',') if c.strip()]

        for clause in clauses:
            parts = clause.split('=')
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()

                # Resolve attribute name
                attr_name = expr_names.get(left, left)

                # Resolve value
                if right in expr_vals:
                    val = expr_vals[right]
                else:
                    val = right

                target_item[attr_name] = val

        self.storage.save_item(self.table_name, target_id, target_item)
        return {'Attributes': copy.deepcopy(target_item)}

    def delete_item(self, Key: Dict[str, Any]) -> Dict[str, Any]:
        table_data = self.storage.get_table_data(self.table_name)
        target_id = None
        for pk_val in Key.values():
            if str(pk_val) in table_data:
                target_id = str(pk_val)
                break

        if not target_id:
            for item_id, it in table_data.items():
                if all(it.get(k) == v for k, v in Key.items()):
                    target_id = item_id
                    break

        if target_id:
            self.storage.delete_item(self.table_name, target_id)

        return {'ResponseMetadata': {'HTTPStatusCode': 200}}


class LocalDynamoDBResource:
    """Simulates boto3.resource('dynamodb')."""
    def __init__(self):
        self._tables = {}

    def Table(self, table_name: str) -> LocalDynamoDBTable:
        if table_name not in self._tables:
            self._tables[table_name] = LocalDynamoDBTable(table_name)
        return self._tables[table_name]


class LocalDynamoDBClientMock:
    """Simulates boto3.client('dynamodb') for table administration scripts."""
    def get_waiter(self, waiter_name: str):
        class DummyWaiter:
            def wait(self, **kwargs):
                pass
        return DummyWaiter()

    def create_table(self, **kwargs):
        table_name = kwargs.get('TableName', 'default-table')
        logger.info(f"[Local DynamoDB] Simulated create_table for '{table_name}'")
        return {'TableDescription': {'TableName': table_name, 'TableStatus': 'ACTIVE'}}

    def describe_table(self, **kwargs):
        table_name = kwargs.get('TableName', 'default-table')
        return {'Table': {'TableName': table_name, 'TableStatus': 'ACTIVE'}}
