#!/usr/bin/env python3
"""
Initialize DynamoDB tables for MedTrack
Run this script after setting up AWS credentials
"""

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config
from app.models.dynamodb import db


def create_table(table_name, key_schema, attribute_definitions, global_secondary_indexes=None, billing_mode='PAY_PER_REQUEST'):
    """Create a DynamoDB table"""
    try:
        client = db.client
        
        params = {
            'TableName': table_name,
            'KeySchema': key_schema,
            'AttributeDefinitions': attribute_definitions,
            'BillingMode': billing_mode
        }
        
        if global_secondary_indexes:
            params['GlobalSecondaryIndexes'] = global_secondary_indexes
        
        client.create_table(**params)
        
        waiter = client.get_waiter('table_exists')
        waiter.wait(TableName=table_name)
        
        print(f"[OK] Created table: {table_name}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"[OK] Table already exists: {table_name}")
            return True
        else:
            print(f"[ERROR] Error creating table {table_name}: {e}")
            return False


def main():
    if not Config.is_aws_mode():
        print("=" * 65)
        print("MEDTRACK - LOCAL STORAGE MODE ACTIVE")
        print("=" * 65)
        print("No AWS credentials detected. Initializing local persistent storage...")
        from app.models.local_storage import LocalStorageManager
        storage = LocalStorageManager()
        storage._load()
        print(f"[OK] Local database ready at: {storage.db_file}")
        print("[OK] Default seed accounts ready:")
        print("    * Admin:   admin@medtrack.com   / Admin@12345")
        print("    * Doctor:  doctor@medtrack.com  / Doctor@12345")
        print("    * Patient: patient@medtrack.com / Patient@12345")
        print()
        print("NOTE: To provision AWS tables, attach an EC2 IAM instance role")
        print("or configure another Boto3 credential provider, then retry.")
        print("=" * 65)
        return

    print("Initializing MedTrack AWS DynamoDB tables...")
    print(f"Region: {Config.AWS_REGION}")
    print()
    
    tables = [
        {
            'name': Config.DYNAMODB_USERS_TABLE,
            'key_schema': [
                {'AttributeName': 'UserID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'UserID', 'AttributeType': 'S'},
                {'AttributeName': 'Email', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'EmailIndex',
                    'KeySchema': [{'AttributeName': 'Email', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'name': Config.DYNAMODB_DOCTORS_TABLE,
            'key_schema': [
                {'AttributeName': 'DoctorID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'DoctorID', 'AttributeType': 'S'},
                {'AttributeName': 'UserID', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'UserIDIndex',
                    'KeySchema': [{'AttributeName': 'UserID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'name': Config.DYNAMODB_PATIENTS_TABLE,
            'key_schema': [
                {'AttributeName': 'PatientID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'PatientID', 'AttributeType': 'S'},
                {'AttributeName': 'UserID', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'UserIDIndex',
                    'KeySchema': [{'AttributeName': 'UserID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'name': Config.DYNAMODB_APPOINTMENTS_TABLE,
            'key_schema': [
                {'AttributeName': 'AppointmentID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'AppointmentID', 'AttributeType': 'S'},
                {'AttributeName': 'PatientID', 'AttributeType': 'S'},
                {'AttributeName': 'DoctorID', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'PatientIDIndex',
                    'KeySchema': [{'AttributeName': 'PatientID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                },
                {
                    'IndexName': 'DoctorIDIndex',
                    'KeySchema': [{'AttributeName': 'DoctorID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'name': Config.DYNAMODB_DIAGNOSIS_TABLE,
            'key_schema': [
                {'AttributeName': 'DiagnosisID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'DiagnosisID', 'AttributeType': 'S'},
                {'AttributeName': 'AppointmentID', 'AttributeType': 'S'},
                {'AttributeName': 'PatientID', 'AttributeType': 'S'},
                {'AttributeName': 'DoctorID', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'AppointmentIDIndex',
                    'KeySchema': [{'AttributeName': 'AppointmentID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                },
                {
                    'IndexName': 'PatientIDIndex',
                    'KeySchema': [{'AttributeName': 'PatientID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                },
                {
                    'IndexName': 'DoctorIDIndex',
                    'KeySchema': [{'AttributeName': 'DoctorID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'name': Config.DYNAMODB_NOTIFICATIONS_TABLE,
            'key_schema': [
                {'AttributeName': 'NotificationID', 'KeyType': 'HASH'}
            ],
            'attribute_definitions': [
                {'AttributeName': 'NotificationID', 'AttributeType': 'S'},
                {'AttributeName': 'UserID', 'AttributeType': 'S'}
            ],
            'gsis': [
                {
                    'IndexName': 'UserIDIndex',
                    'KeySchema': [{'AttributeName': 'UserID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        }
    ]
    
    all_success = True
    for table in tables:
        gsi_list = []
        for gsi in table.get('gsis', []):
            gsi_list.append({
                'IndexName': gsi['IndexName'],
                'KeySchema': gsi['KeySchema'],
                'Projection': gsi['Projection'],
                'ProvisionedThroughput': gsi.get('ProvisionedThroughput', {
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                })
            })
        
        success = create_table(
            table['name'],
            table['key_schema'],
            table['attribute_definitions'],
            gsi_list if gsi_list else None
        )
        if not success:
            all_success = False
    
    print()
    if all_success:
        print("✓ All tables initialized successfully!")
    else:
        print("✗ Some tables failed to initialize")
        sys.exit(1)


if __name__ == '__main__':
    main()
