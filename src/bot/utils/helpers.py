from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .user_role import get_user_role

from ..config.settings import (
    Roles,
    PHOTOS_DIR
)

logger = logging.getLogger(__name__)


def get_greeting() -> str:
    """Get a time-appropriate greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    elif hour < 17:
        return "Good Afternoon"
    else:
        return "Good Evening"

async def safe_edit_text(
    message: Any,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None
) -> Any:
    """Safely edit a message's text, falling back to sending a new message if editing fails."""
    try:
        if hasattr(message, 'text') and message.text and message.text.strip():
            return await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            return await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except Exception as e:
        logger.error(f"Error in safe_edit_text: {str(e)}")
        try:
            return await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Failed to send fallback message: {str(e)}")
            return None

def build_menu(
    buttons: List[InlineKeyboardButton],
    n_cols: int = 2,
    header_buttons: Optional[List[InlineKeyboardButton]] = None,
    footer_buttons: Optional[List[InlineKeyboardButton]] = None
) -> List[List[InlineKeyboardButton]]:
    """Build a menu with a specified number of columns."""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu

def save_photo(photo_file: Any, job_id: int) -> str:
    """Save a photo file and return its path."""
    PHOTOS_DIR.mkdir(exist_ok=True)
    photo_filename = f"job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    photo_path = PHOTOS_DIR / photo_filename
    return str(photo_path)

def format_duration(start_time: datetime, finish_time: Optional[datetime] = None) -> str:
    """Format the duration between two timestamps."""
    if not finish_time:
        finish_time = datetime.now()
    
    duration = finish_time - start_time
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if duration.days > 0:
        return f"{duration.days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def validate_user_access(update: Update, required_role: str) -> bool:
    """Validate if a user has the required role access."""
    user_id = update.effective_user.id
    user_role = get_user_role(user_id)
    
    if required_role == Roles.DEV:
        return user_role == Roles.DEV
    elif required_role == Roles.DIRECTOR:
        return user_role in [Roles.DEV, Roles.DIRECTOR]
    elif required_role == Roles.EMPLOYEE:
        return user_role in [Roles.DEV, Roles.DIRECTOR, Roles.EMPLOYEE]
    
    return False 