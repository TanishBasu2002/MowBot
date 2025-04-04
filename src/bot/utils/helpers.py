from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pathlib import Path
import logging
from telegram import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    Update, 
    Message,
    CallbackQuery
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ..config.settings import Roles, PHOTOS_DIR
from .user_role import get_user_role

logger = logging.getLogger(__name__)

class Helpers:
    """Utility class containing helper methods for the bot."""
    
    # --- Message Utilities ---
    @staticmethod
    async def safe_edit_text(
        message: Union[Message, CallbackQuery],
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None,
        disable_web_page_preview: bool = True
    ) -> Optional[Message]:
        """
        Safely edit message text with comprehensive error handling.
        
        Args:
            message: The message or callback query to edit
            text: New message text
            reply_markup: Optional inline keyboard
            parse_mode: Text formatting mode
            disable_web_page_preview: Disable link previews
            
        Returns:
            The edited Message or None if failed
        """
        try:
            if isinstance(message, CallbackQuery):
                return await message.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
            elif hasattr(message, 'edit_text'):
                return await message.edit_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
            else:
                return await message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
                
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return None  # Silent handling for no changes
            logger.warning(f"Message edit failed: {e}")
            try:
                return await message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception as fallback_error:
                logger.error(f"Fallback message failed: {fallback_error}")
                return None
                
        except Exception as e:
            logger.error(f"Unexpected error in safe_edit_text: {e}")
            return None

    # --- UI Components ---
    @staticmethod
    def build_menu(
        buttons: List[InlineKeyboardButton],
        n_cols: int = 2,
        header_buttons: Optional[List[InlineKeyboardButton]] = None,
        footer_buttons: Optional[List[InlineKeyboardButton]] = None
    ) -> List[List[InlineKeyboardButton]]:
        """
        Build a responsive menu layout with specified columns.
        
        Args:
            buttons: List of buttons to arrange
            n_cols: Number of columns
            header_buttons: Buttons to place at top
            footer_buttons: Buttons to place at bottom
            
        Returns:
            List of button rows
        """
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    # --- File Handling ---
    @staticmethod
    def save_photo(photo_file: Any, job_id: int) -> Optional[Path]:
        """
        Save a photo to disk with proper error handling.
        
        Args:
            photo_file: Telegram photo file object
            job_id: Associated job ID for naming
            
        Returns:
            Path to saved photo or None if failed
        """
        try:
            PHOTOS_DIR.mkdir(exist_ok=True, parents=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            photo_path = PHOTOS_DIR / f"job_{job_id}_{timestamp}.jpg"
            
            with open(photo_path, 'wb') as f:
                photo_file.download(out=f)
                
            return photo_path
        except Exception as e:
            logger.error(f"Failed to save photo: {e}")
            return None

    # --- Time Utilities ---
    @staticmethod
    def get_greeting() -> str:
        """Get a time-appropriate greeting with emoji."""
        hour = datetime.now().hour
        if hour < 6:
            return "🌃 Good Night"
        elif hour < 12:
            return "🌅 Good Morning"
        elif hour < 17:
            return "☀️ Good Afternoon"
        else:
            return "🌆 Good Evening"

    @staticmethod
    def format_duration(
        start_time: datetime, 
        end_time: Optional[datetime] = None,
        include_seconds: bool = False
    ) -> str:
        """
        Format duration between two timestamps.
        
        Args:
            start_time: Start datetime
            end_time: End datetime (defaults to now)
            include_seconds: Whether to show seconds
            
        Returns:
            Formatted duration string
        """
        end_time = end_time or datetime.now()
        duration = end_time - start_time
        
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours:02d}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes:02d}m")
        if include_seconds:
            parts.append(f"{seconds:02d}s")
            
        return " ".join(parts) if parts else "0m"

    # --- Data Processing ---
    @staticmethod
    def chunk_list(
        items: List[Any], 
        chunk_size: int, 
        fill_value: Any = None
    ) -> List[List[Any]]:
        """
        Split list into chunks with optional padding.
        
        Args:
            items: List to chunk
            chunk_size: Size of each chunk
            fill_value: Value to pad last chunk if needed
            
        Returns:
            List of chunks
        """
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        if fill_value is not None and chunks and len(chunks[-1]) < chunk_size:
            chunks[-1].extend([fill_value] * (chunk_size - len(chunks[-1])))
        return chunks

    # --- Security ---
    @staticmethod
    def validate_user_access(update: Update, required_role: str) -> bool:
        """
        Check if user has required access level.
        
        Args:
            update: Telegram update object
            required_role: Minimum required role
            
        Returns:
            bool: True if access granted
        """
        user_id = update.effective_user.id
        user_role = get_user_role(user_id)
        
        role_hierarchy = {
            Roles.DEV: [Roles.DEV],
            Roles.DIRECTOR: [Roles.DEV, Roles.DIRECTOR],
            Roles.EMPLOYEE: [Roles.DEV, Roles.DIRECTOR, Roles.EMPLOYEE],
            Roles.GENERIC: [Roles.DEV, Roles.DIRECTOR, Roles.EMPLOYEE, Roles.GENERIC]
        }
        
        return user_role in role_hierarchy.get(required_role, [])