from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..utils.helpers import safe_edit_text, build_menu
from ..database.models import get_db
from ..services.ground_service import GroundService

class BaseHandler:
    """Base class for all handlers."""
    
    def __init__(self):
        self.ground_service = GroundService()

    async def _get_db(self) -> Session:
        """Get a database session."""
        return next(get_db())

    async def _send_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None
    ) -> Any:
        """Send a message, handling both new messages and callback queries."""
        if update.callback_query:
            return await safe_edit_text(
                update.callback_query.message,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        return await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

    def _build_menu(
        self,
        buttons: List[Dict[str, str]],
        n_cols: int = 2,
        header_buttons: Optional[List[Dict[str, str]]] = None,
        footer_buttons: Optional[List[Dict[str, str]]] = None
    ) -> InlineKeyboardMarkup:
        """Build a menu from button dictionaries."""
        def create_button(button_dict: Dict[str, str]):
            return InlineKeyboardButton(
                text=button_dict['text'],
                callback_data=button_dict.get('callback_data', ''),
                url=button_dict.get('url', None)
            )

        keyboard_buttons = [create_button(b) for b in buttons]
        header = [create_button(b) for b in (header_buttons or [])]
        footer = [create_button(b) for b in (footer_buttons or [])]

        return InlineKeyboardMarkup(
            build_menu(keyboard_buttons, n_cols, header, footer)
        )

    async def handle_error(
        self,
        update: Update,
        error: Exception,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None
    ) -> None:
        """Handle errors in handlers."""
        error_message = f"❌ An error occurred: {str(error)}"
        await self._send_message(update, error_message)

    @staticmethod
    def get_callback_data(update: Update) -> str:
        """Get callback data from an update."""
        return update.callback_query.data if update.callback_query else ""

    @staticmethod
    def get_user_id(update: Update) -> int:
        """Get the user ID from an update."""
        return update.effective_user.id 