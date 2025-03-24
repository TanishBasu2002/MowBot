from functools import wraps
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes

from .helpers import validate_user_access, safe_edit_text
from ..config.settings import Roles

def require_role(required_role: str):
    """Decorator to check if a user has the required role."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
            if not validate_user_access(update, required_role):
                message = "🚫 You don't have permission to access this feature."
                if update.callback_query:
                    await safe_edit_text(update.callback_query.message, message)
                else:
                    await update.message.reply_text(message)
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

def dev_only(func: Callable):
    """Decorator for dev-only functions."""
    return require_role(Roles.DEV)(func)

def director_only(func: Callable):
    """Decorator for director-only functions."""
    return require_role(Roles.DIRECTOR)(func)

def employee_required(func: Callable):
    """Decorator for employee-required functions."""
    return require_role(Roles.EMPLOYEE)(func)

def error_handler(func: Callable):
    """Decorator to handle errors in bot commands."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            error_message = f"❌ An error occurred: {str(e)}"
            if update.callback_query:
                await safe_edit_text(update.callback_query.message, error_message)
            else:
                await update.message.reply_text(error_message)
            raise
    return wrapper 