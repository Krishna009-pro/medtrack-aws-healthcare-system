import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import Config
from app.models import (
    user_model, doctor_model, patient_model,
    appointment_model, diagnosis_model, notification_model
)
from app.services.sns import sns_service


@pytest.fixture
def client():
    app = create_app('testing')
    with app.test_client() as client:
        yield client


class TestLocalModeExecution:
    def test_mode_detection(self):
        # Without AWS credentials in testing environment, mode should be 'local'
        assert Config.is_aws_mode() is False
        assert Config.get_mode() == 'local'

    def test_health_check_endpoint(self, client):
        res = client.get('/health')
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'medtrack'
        assert data['mode'] == 'local'
        assert data['aws_enabled'] is False

    def test_admin_flow(self, client):
        # Login as Admin
        res = client.post('/auth/login', data={'email': 'admin@medtrack.com', 'password': 'Admin@12345'}, follow_redirects=True)
        assert res.status_code == 200
        assert b'Admin' in res.data
        assert b'Local Mode' in res.data

        # View Users list
        users_res = client.get('/admin/users')
        assert users_res.status_code == 200
        assert b'System Administrator' in users_res.data
        client.get('/auth/logout')

    def test_doctor_flow(self, client):
        # Login as Doctor
        res = client.post('/auth/login', data={'email': 'doctor@medtrack.com', 'password': 'Doctor@12345'}, follow_redirects=True)
        assert res.status_code == 200
        assert b'Dr. Sarah Jenkins' in res.data

        # Check schedule
        schedule_res = client.get('/doctor/schedule')
        assert schedule_res.status_code == 200

        # View notifications
        notif_res = client.get('/doctor/notifications')
        assert notif_res.status_code == 200
        client.get('/auth/logout')

    def test_patient_booking_and_sns_dispatch(self, client):
        # Login as Patient
        res = client.post('/auth/login', data={'email': 'patient@medtrack.com', 'password': 'Patient@12345'}, follow_redirects=True)
        assert res.status_code == 200

        # Book an appointment
        book_res = client.post('/patient/book', data={
            'doctor_id': 'doc-001',
            'date': '2026-11-20',
            'time': '14:00'
        }, follow_redirects=True)
        assert book_res.status_code == 200
        assert b'Appointment booked successfully' in book_res.data or b'November 20, 2026' in book_res.data

        # Verify SNS dispatched locally
        log_file = os.path.join(Config.DATA_DIR, 'sns_notifications.log')
        assert os.path.exists(log_file)
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'Appointment Booked' in content
        client.get('/auth/logout')

    def test_registration_and_persistence(self, client):
        email = "test.persistent@example.com"
        # Register
        reg = client.post('/auth/register', data={
            'email': email,
            'name': 'Persistent User',
            'password': 'Password@12345',
            'confirm_password': 'Password@12345',
            'role': 'Patient',
            'phone': '+1-555-8888',
            'age': '40',
            'medical_history': 'None'
        }, follow_redirects=True)
        assert reg.status_code == 200

        # Fetch directly from model
        saved_user = user_model.get_by_email(email)
        assert saved_user is not None
        assert saved_user['Name'] == 'Persistent User'
