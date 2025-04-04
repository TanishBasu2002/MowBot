# file: /src/bot/utils/message_templates.py
from asyncio.log import logger
import logging
from typing import Optional, List, Dict
from datetime import datetime

from telegram import Update

class MessageTemplates:
    """Professional message templates for consistent UI."""

    # Styling constants
    SEPARATOR = "─" * 32
    BULLET = "•"
    
    # Status indicators with better emojis
    STATUS_EMOJIS = {
        'pending': '⭐',      # More visible than hourglass
        'in_progress': '🔵',  # Clear blue dot for active
        'completed': '✅',    # Classic checkmark
        'cancelled': '🔴',    # Red for cancelled
        'delayed': '⚠️',      # Warning for delayed
        'unknown': '❓'       # Question for unknown
    }

    @staticmethod
    def format_job_card(
        site_name: str,
        status: str,
        area: Optional[str] = None,
        duration: Optional[str] = None,
        notes: Optional[str] = None,
        photo_count: Optional[int] = None,
        priority: Optional[str] = None
    ) -> str:
        """Format a job card with enhanced styling."""
        status_emoji = MessageTemplates.STATUS_EMOJIS.get(status.lower(), MessageTemplates.STATUS_EMOJIS['unknown'])
        priority_indicator = "🔥 HIGH PRIORITY\n" if priority == "high" else ""
        
        # Header with priority and site name
        header = f"{priority_indicator}📍 {site_name.upper()}"
        
        # Status line with custom formatting
        status_line = f"{status_emoji} Status: {status.title()}"
        
        # Details section with bullet points
        details = []
        if area:
            details.append(f"{MessageTemplates.BULLET} Area: {area}")
        if duration:
            details.append(f"{MessageTemplates.BULLET} Duration: {duration}")
        if photo_count is not None:
            details.append(f"{MessageTemplates.BULLET} Photos: {photo_count}")
        
        # Notes section with special formatting
        notes_section = f"\n📝 Notes:\n{notes}" if notes else ""
        
        # Combine all sections with proper spacing
        sections = [
            header,
            status_line,
            "\n".join(details) if details else "",
            notes_section
        ]
        
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def format_dashboard_header(name: str, role: str) -> str:
        """Format an enhanced dashboard header."""
        greeting = MessageTemplates.get_greeting()
        current_time = datetime.now().strftime("%I:%M %p")
        
        header = [
            f"{greeting}, {name}!",
            f"🕒 Current Time: {current_time}",
            "",
            f"🎯 {role.upper()} DASHBOARD",
            MessageTemplates.SEPARATOR
        ]
        
        return "\n".join(header)

    @staticmethod
    def format_photo_progress(current: int, total: int) -> str:
        """Format an enhanced photo upload progress message."""
        progress = min(current / total * 20, 20)  # Doubled the bar length
        bar = "█" * int(progress) + "░" * (20 - int(progress))
        percentage = int((current / total) * 100)
        
        return (
            f"📸 Photo Upload Progress\n"
            f"{bar}\n"
            f"{current}/{total} ({percentage}%)"
        )

    @staticmethod
    def format_job_list_header(date: Optional[str] = None, count: Optional[int] = None) -> str:
        """Format an enhanced job list header."""
        date_str = f" for {date}" if date else ""
        count_str = f" ({count} jobs)" if count is not None else ""
        
        return (
            f"📋 Jobs{date_str}{count_str}\n"
            f"{MessageTemplates.SEPARATOR}"
        )

    @staticmethod
    def format_error_message(error: str, details: Optional[str] = None) -> str:
        """Format an enhanced error message."""
        details_section = f"\n{details}" if details else ""
        return (
            f"⚠️ Error Occurred\n"
            f"{MessageTemplates.SEPARATOR}\n"
            f"{error}{details_section}"
        )

    @staticmethod
    def format_success_message(message: str, details: Optional[str] = None) -> str:
        """Format an enhanced success message."""
        detail_section = f"\n{details}" if details else ""
        return f"✅ Success!\n{message}{detail_section}"

    @staticmethod
    def get_greeting() -> str:
        """Get an enhanced time-appropriate greeting."""
        hour = datetime.now().hour
        if hour < 6:
            return "🌃 Good Night"
        elif hour < 12:
            return "🌅 Good Morning"
        elif hour < 17:
            return "☀️ Good Afternoon"
        elif hour < 22:
            return "🌆 Good Evening"
        else:
            return "🌃 Good Night"

    @staticmethod
    def format_site_info(
        site_name: str,
        contact: Optional[str] = None,
        gate_code: Optional[str] = None,
        address: Optional[str] = None,
        special_instructions: Optional[str] = None
    ) -> str:
        """Format enhanced site information."""
        sections = [f"📍 {site_name.upper()}\n{MessageTemplates.SEPARATOR}"]
        
        if contact:
            sections.append(f"👤 Contact:\n{contact}")
        if gate_code:
            sections.append(f"🔑 Gate Code:\n{gate_code}")
        if address:
            sections.append(f"📍 Address:\n{address}")
        if special_instructions:
            sections.append(f"ℹ️ Special Instructions:\n{special_instructions}")
        
        if len(sections) == 1:
            sections.append("ℹ️ No additional information available")
        
        return "\n\n".join(sections)

    @staticmethod
    def format_duration_tracker(
        start_time: datetime,
        end_time: Optional[datetime] = None,
        include_seconds: bool = False
    ) -> str:
        """Format an enhanced duration tracker."""
        if not end_time:
            end_time = datetime.now()
        
        duration = end_time - start_time
        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        seconds = duration.seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours:02d}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes:02d}m")
        if include_seconds:
            parts.append(f"{seconds:02d}s")
            
        duration_str = " ".join(parts)
        return f"⏱️ Duration: {duration_str}"

    @staticmethod
    def format_stats_header(period: str = "Today") -> str:
        """Format a statistics header."""
        return (
            f"📊 Statistics for {period}\n"
            f"{MessageTemplates.SEPARATOR}"
        ) 
    @staticmethod
    def format_job_card(site_name: str, status: str, area: Optional[str] = None,
                       duration: Optional[str] = None, notes: Optional[str] = None,
                       photo_count: Optional[int] = None) -> str:
        """Enhanced job card with notes section"""
        card = [
            f"📍 {site_name.upper()}",
            f"🔄 Status: {status.title()}",
            f"📏 Area: {area}" if area else "",
            f"⏱ Duration: {duration}" if duration else "",
            f"📸 Photos: {photo_count}" if photo_count is not None else "",
            "",
            "📝 NOTES:",
            notes if notes else "No notes yet"
        ]
        return "\n".join([line for line in card if line])
    @staticmethod
    def format_note(
        author: str,
        timestamp: str,
        note: str,
        has_photo: bool = False
    ) -> str:
        """Format a single note entry"""
        photo_indicator = " 📸" if has_photo else ""
        return (
            f"👤 {author} at {timestamp}{photo_indicator}:\n"
            f"{note}\n"
            f"{MessageTemplates.SEPARATOR}"
        )
    
    @staticmethod
    def format_notes_list(notes: List[Dict]) -> str:
        """Format multiple notes"""
        if not notes:
            return "No notes yet for this job."
            
        header = "📝 JOB NOTES:\n" + MessageTemplates.SEPARATOR
        return header + "\n".join(
            MessageTemplates.format_note(
                note['author'],
                note['created_at'],
                note['note'],
                note['has_photo']
            ) for note in notes
        )
    logger = logging.getLogger(__name__)

    async def safe_edit_text(update: Update, text: str, reply_markup=None, parse_mode=None):
        """Safely edit message text with fallback to new message"""
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                await update.effective_message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as e:
            if "Message is not modified" in str(e):
                return  # Silent handling for no-change edits
            logger.warning(f"Message edit failed: {e}")
            try:
                await update.effective_message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception as fallback_error:
                logger.error(f"Fallback failed: {fallback_error}")
        except Exception as e:
            logger.error(f"Unexpected edit error: {e}")
            await update.effective_message.reply_text(
                "⚠️ Please try that action again",
                reply_markup=reply_markup
            )