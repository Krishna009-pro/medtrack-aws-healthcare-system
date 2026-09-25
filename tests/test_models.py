import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.dynamodb import (
    UserModel, DoctorModel, PatientModel,
    AppointmentModel, DiagnosisModel, NotificationModel
)
from app.utils.auth import hash_password, verify_password
from app.utils.helpers import (
    format_date, format_time, generate_time_slots,
    get_available_slots, validate_appointment_data, paginate_items
)


class TestAuth:
    def test_hash_password(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed != password
        assert len(hashed) > 50

    def test_verify_password(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False


class TestHelpers:
    def test_format_date(self):
        assert format_date("2024-01-15") == "January 15, 2024"
        assert format_date("2024-12-25") == "December 25, 2024"

    def test_format_time(self):
        assert format_time("09:00") == "09:00 AM"
        assert format_time("14:30") == "02:30 PM"
        assert format_time("23:59") == "11:59 PM"

    def test_generate_time_slots(self):
        slots = generate_time_slots(9, 12, 30)
        assert slots == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]

    def test_get_available_slots(self):
        booked = ["09:30", "10:00"]
        available = get_available_slots("doc1", "2026-10-15", booked)
        assert "09:30" not in available
        assert "10:00" not in available
        assert "09:00" in available
        assert "10:30" in available

    def test_validate_appointment_data_valid(self):
        from datetime import datetime, timedelta
        future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        data = {
            'doctor_id': 'doc1',
            'date': future_date,
            'time': '10:00'
        }
        errors = validate_appointment_data(data)
        assert errors == {}

    def test_validate_appointment_data_missing_fields(self):
        data = {}
        errors = validate_appointment_data(data)
        assert 'doctor_id' in errors
        assert 'date' in errors
        assert 'time' in errors

    def test_validate_appointment_data_past_date(self):
        data = {
            'doctor_id': 'doc1',
            'date': '2020-01-01',
            'time': '10:00'
        }
        errors = validate_appointment_data(data)
        assert 'date' in errors

    def test_paginate_items(self):
        items = list(range(25))
        result = paginate_items(items, page=1, per_page=10)
        assert len(result['items']) == 10
        assert result['total'] == 25
        assert result['pages'] == 3
        assert result['has_next'] is True
        assert result['has_prev'] is False

        result = paginate_items(items, page=3, per_page=10)
        assert len(result['items']) == 5
        assert result['has_next'] is False
        assert result['has_prev'] is True


class TestModels:
    @patch('app.models.dynamodb.db')
    def test_user_model_create(self, mock_db):
        mock_table = Mock()
        mock_db.get_table.return_value = mock_table
        
        model = UserModel()
        model.table = mock_table
        
        user = model.create_user(
            email="test@example.com",
            name="Test User",
            password_hash="hashed_password",
            role="Patient",
            phone="+15551234567"
        )
        
        assert user['Email'] == "test@example.com"
        assert user['Name'] == "Test User"
        assert user['Role'] == "Patient"
        assert user['Phone'] == "+15551234567"
        mock_table.put_item.assert_called_once()

    @patch('app.models.dynamodb.db')
    def test_doctor_model_create(self, mock_db):
        mock_table = Mock()
        mock_db.get_table.return_value = mock_table
        
        model = DoctorModel()
        model.table = mock_table
        
        doctor = model.create_doctor(
            user_id="user123",
            specialization="Cardiology",
            experience=10
        )
        
        assert doctor['UserID'] == "user123"
        assert doctor['Specialization'] == "Cardiology"
        assert doctor['Experience'] == 10

    @patch('app.models.dynamodb.db')
    def test_patient_model_create(self, mock_db):
        mock_table = Mock()
        mock_db.get_table.return_value = mock_table
        
        model = PatientModel()
        model.table = mock_table
        
        patient = model.create_patient(
            user_id="user123",
            age=30,
            medical_history="No known conditions"
        )
        
        assert patient['UserID'] == "user123"
        assert patient['Age'] == 30
        assert patient['MedicalHistory'] == "No known conditions"

    @patch('app.models.dynamodb.db')
    def test_appointment_model_create(self, mock_db):
        mock_table = Mock()
        mock_db.get_table.return_value = mock_table
        
        model = AppointmentModel()
        model.table = mock_table
        
        appointment = model.create_appointment(
            patient_id="pat123",
            doctor_id="doc123",
            date="2024-01-15",
            time="10:00"
        )
        
        assert appointment['PatientID'] == "pat123"
        assert appointment['DoctorID'] == "doc123"
        assert appointment['Date'] == "2024-01-15"
        assert appointment['Time'] == "10:00"
        assert appointment['Status'] == "Pending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])