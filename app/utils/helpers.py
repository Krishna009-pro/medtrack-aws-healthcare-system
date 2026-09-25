from datetime import datetime, timedelta
from typing import List, Dict, Any


def format_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%B %d, %Y')
    except ValueError:
        return date_str


def format_time(time_str: str) -> str:
    try:
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%I:%M %p')
    except ValueError:
        return time_str


def generate_time_slots(start_hour: int = 9, end_hour: int = 17, interval: int = 30) -> List[str]:
    slots = []
    current = datetime(2000, 1, 1, start_hour, 0)
    end = datetime(2000, 1, 1, end_hour, 0)
    while current < end:
        slots.append(current.strftime('%H:%M'))
        current += timedelta(minutes=interval)
    return slots


def get_available_slots(doctor_id: str, date: str, booked_slots: List[str]) -> List[str]:
    all_slots = generate_time_slots()
    return [slot for slot in all_slots if slot not in booked_slots]


def validate_appointment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    errors = {}
    required_fields = ['doctor_id', 'date', 'time']
    for field in required_fields:
        if not data.get(field):
            errors[field] = f'{field.replace("_", " ").title()} is required'

    if data.get('date'):
        try:
            apt_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            if apt_date < datetime.now().date():
                errors['date'] = 'Appointment date cannot be in the past'
        except ValueError:
            errors['date'] = 'Invalid date format (YYYY-MM-DD)'

    if data.get('time'):
        try:
            datetime.strptime(data['time'], '%H:%M')
        except ValueError:
            errors['time'] = 'Invalid time format (HH:MM)'

    return errors


def paginate_items(items: List[Any], page: int, per_page: int = 10) -> Dict[str, Any]:
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        'items': items[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'has_prev': page > 1,
        'has_next': page * per_page < total
    }