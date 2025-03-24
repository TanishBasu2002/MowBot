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
DEV_USERS: Set[int] = {1672989849}
DIRECTOR_USERS: Set[int] = {1672989849, 7996550019, 8018680694}
EMPLOYEE_USERS: Dict[int, str] = {1672989849: "Andy", 6396234665: "Alex"}

# Database Configuration
DATABASE_PATH = BASE_DIR / "bot_data.db"
PHOTOS_DIR = BASE_DIR / "photos"

# Job Configuration
MAX_PHOTOS_PER_JOB = 25
PHOTOS_CHUNK_SIZE = 10

# Scheduler Configuration
RESET_JOBS_HOUR = 0
RESET_JOBS_MINUTE = 0

# Create necessary directories
PHOTOS_DIR.mkdir(exist_ok=True) 