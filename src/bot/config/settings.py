# file: src/bot/config/settings.py
from typing import Dict, Set
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

# User Roles Configuration
class Roles:
    DEV = "Dev"
    DIRECTOR = "Director"
    EMPLOYEE = "Employee"
    GENERIC = "Generic"
# User IDs Configuration
dev_users = {1672989849}         # Replace with your dev Telegram user ID.
director_users = {8018680694, 7996550019}  # Two director IDs.
employee_users = {1672989849: "Andy", 777888999, 7747082939: "Alex"}  # Two employee IDs.

# Database Configuration
DATABASE_PATH = BASE_DIR / "bot_data.db"
PHOTOS_DIR = BASE_DIR / "photos"

# Job Configuration
MAX_PHOTOS_PER_JOB = 50
PHOTOS_CHUNK_SIZE = 10

# Scheduler Configuration
RESET_JOBS_HOUR = 0
RESET_JOBS_MINUTE = 0

# Create necessary directories
PHOTOS_DIR.mkdir(exist_ok=True) 
