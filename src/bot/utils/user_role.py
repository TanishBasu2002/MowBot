# file: /src/bot/utils/user_role.py
from ..config.settings import dev_users, director_users, employee_users

def get_user_role(user_id: int) -> str:
    """Get the role of a user based on their ID."""
    if user_id in dev_users:
        return "Dev"
    elif user_id in director_users:
        return "Director"
    elif user_id in employee_users:
        return "Employee"
    return "Generic"
def get_employee_name(user_id: int) -> str:
    """Get employee name by ID"""
    return employee_users.get(user_id, "Employee")