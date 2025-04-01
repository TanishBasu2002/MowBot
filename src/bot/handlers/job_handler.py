from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..utils.note_service import NoteService
from ..utils.user_role import get_user_role
from ..utils.message_templates import MessageTemplates
from ..utils.button_layouts import ButtonLayouts
from ..database.models import get_db
from ..services.ground_service import GroundService
from ..utils.decorators import error_handler, employee_required
from .base_handler import BaseHandler

class JobHandler(BaseHandler):
    """Handler for job-related operations."""

    def __init__(self):
        super().__init__()

    @error_handler
    @employee_required
    async def view_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int):
        """View a specific job with enhanced UI."""
        db = await self._get_db()
        ground = await self.ground_service.get_ground(db, job_id)
        
        if not ground:
            await self._send_message(
                update,
                MessageTemplates.format_error_message("Job not found", code="JOB_404")
            )
            return

        # Format job card with all available information
        job_card = MessageTemplates.format_job_card(
            site_name=ground.site_name,
            status=ground.status,
            area=ground.area,
            duration=ground.duration,
            notes=ground.notes,
            photo_count=ground.photo_count,
            priority="high" if getattr(ground, 'priority', None) == "high" else None
        )

        # Create context-aware button menu
        markup = ButtonLayouts.create_job_menu(
            job_id=job_id,
            status=ground.status,
            has_photos=bool(ground.photos),
            has_notes=bool(ground.notes)
        )

        await self._send_message(update, job_card, reply_markup=markup)

    @error_handler
    @employee_required
    async def start_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a job with enhanced UI feedback."""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        
        success, message = await self.ground_service.start_job(db, job_id)
        if success:
            await self._send_message(
                update,
                MessageTemplates.format_success_message(
                    "Job started successfully",
                    "Timer has been started. You can now upload photos and add notes."
                )
            )
            await self.view_job(update, context, job_id)
        else:
            await self._send_message(
                update,
                MessageTemplates.format_error_message(message, code="JOB_START_ERR")
            )

    @error_handler
    @employee_required
    async def finish_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete a job with enhanced UI feedback."""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        
        success, message = await self.ground_service.finish_job(db, job_id)
        if success:
            ground = await self.ground_service.get_ground(db, job_id)
            duration = MessageTemplates.format_duration_tracker(
                ground.start_time,
                ground.finish_time,
                include_seconds=True
            )
            
            await self._send_message(
                update,
                MessageTemplates.format_success_message(
                    "Job completed successfully",
                    f"{duration}\nAll information has been saved."
                )
            )
            # Return to job list after completion
            await self.view_employee_jobs(update, context)
        else:
            await self._send_message(
                update,
                MessageTemplates.format_error_message(message, code="JOB_FINISH_ERR")
            )

    @error_handler
    @employee_required
    async def view_employee_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View all jobs assigned to an employee with enhanced UI."""
        user_id = self.get_user_id(update)
        db = await self._get_db()
        grounds = await self.ground_service.get_employee_grounds(db, user_id)
        
        if not grounds:
            await self._send_message(
                update,
                "📋 No jobs assigned for today.",
                reply_markup=ButtonLayouts.create_employee_dashboard()
            )
            return

        # Group jobs by status
        active_jobs = [g for g in grounds if g.status == 'in_progress']
        pending_jobs = [g for g in grounds if g.status == 'pending']
        completed_jobs = [g for g in grounds if g.status == 'completed']

        # Create job list message
        sections = []
        
        # Header with job count
        sections.append(MessageTemplates.format_job_list_header(count=len(grounds)))
        
        # Active jobs section
        if active_jobs:
            sections.append("\n🔵 Active Jobs:")
            for job in active_jobs:
                sections.append(MessageTemplates.format_job_card(
                    site_name=job.site_name,
                    status=job.status,
                    area=job.area,
                    duration=job.duration,
                    photo_count=job.photo_count
                ))

        # Pending jobs section
        if pending_jobs:
            sections.append("\n⭐ Pending Jobs:")
            for job in pending_jobs:
                sections.append(MessageTemplates.format_job_card(
                    site_name=job.site_name,
                    status=job.status,
                    area=job.area
                ))

        # Completed jobs section
        if completed_jobs:
            sections.append("\n✅ Completed Jobs:")
            for job in completed_jobs:
                sections.append(MessageTemplates.format_job_card(
                    site_name=job.site_name,
                    status=job.status,
                    area=job.area,
                    duration=job.duration,
                    photo_count=job.photo_count
                ))

        # Create buttons for each job
        buttons = []
        for job in active_jobs + pending_jobs + completed_jobs:
            status_emoji = MessageTemplates.STATUS_EMOJIS.get(job.status, '❓')
            buttons.append([
                InlineKeyboardButton(
                    f"{status_emoji} {job.site_name}",
                    callback_data=f"job_menu_{job.id}"
                )
            ])
        
        # Add navigation button
        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="emp_employee_dashboard")
        ])

        await self._send_message(
            update,
            "\n\n".join(sections), 
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    async def view_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int):
        """View job with notes"""
        db = await self._get_db()
        ground = await self.ground_service.get_ground(db, job_id)
        
        # Get all notes for this job
        notes = NoteService.get_notes_for_job(db, job_id)
        
        # Format job card with notes
        job_card = MessageTemplates.format_job_card(
            site_name=ground.site_name,
            status=ground.status,
            area=ground.area,
            duration=ground.duration,
            notes="\n\n".join([f"{n['author_role']} ({n['created_at']}): {n['note']}" for n in notes]),
            photo_count=ground.photo_count
        )
        
        # Create buttons including note addition
        buttons = []
        buttons.append([InlineKeyboardButton("📝 Add Note", callback_data=f"add_note_{job_id}")])
        # ... rest of your existing buttons ...
        
        markup = InlineKeyboardMarkup(buttons)
        await self._send_message(update, job_card, reply_markup=markup)

    async def add_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start note addition process"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        context.user_data["awaiting_note_for"] = job_id
        await self._send_message(update, "Please enter your note for this job:")
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages, including notes"""
        if "awaiting_note_for" in context.user_data:
            job_id = context.user_data.pop("awaiting_note_for")
            note_text = update.message.text
            user_id = self.get_user_id(update)
            user_role = get_user_role(user_id)
            
            db = await self._get_db()
            NoteService.add_note(db, job_id, user_id, user_role, note_text)
            
            await self._send_message(
                update,
                MessageTemplates.format_success_message("Note Added", "Your note has been saved."),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Job", callback_data=f"job_menu_{job_id}")]
                ])
            )
            await self.view_job(update, context, job_id)
        else:
            # Handle other text messages if needed
            pass