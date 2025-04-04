from datetime import datetime
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..utils.helpers import Helpers

from ..utils.note_service import NoteService
from ..utils.user_role import get_employee_name, get_user_role
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
        """Start a job with note-taking capability"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        
        # Start the job
        success, message = await self.ground_service.start_job(db, job_id)
        if success:
            # Create job working interface
            buttons = [
                [InlineKeyboardButton("📝 Add Note", callback_data=f"add_note_{job_id}")],
                [InlineKeyboardButton("✅ Finish Job", callback_data=f"finish_job_{job_id}")]
            ]
            
            await self._send_message(
                update,
                "🛠️ Job started! You can now add notes about your work.\n"
                "Click 'Add Note' to document your progress or 'Finish Job' when done.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await self._send_message(update, message)

    @error_handler
    @employee_required
    async def add_note_to_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prepare to receive a note for the current job"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        context.user_data["awaiting_note_for"] = job_id
        
        await self._send_message(
            update,
            "✏️ Please enter your note about this job:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data=f"job_menu_{job_id}")]
            ])
        )

    @error_handler
    @employee_required
    async def handle_job_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process a submitted job note"""
        if "awaiting_note_for" not in context.user_data:
            return

        job_id = context.user_data.pop("awaiting_note_for")
        note_text = update.message.text
        user_id = self.get_user_id(update)
        user_name = get_employee_name(user_id)
        user_role = get_user_role(user_id)
        
        db = await self._get_db()
        NoteService.add_note(db, job_id, user_id, user_name, user_role, note_text)
        
        # Return to job menu
        await self._send_message(
            update,
            MessageTemplates.format_success_message("Note added successfully!"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Job", callback_data=f"job_menu_{job_id}")]
            ])
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
        """Handle text input for notes with proper error handling"""
        if "awaiting_note_for" not in context.user_data:
            return

        job_id = context.user_data.pop("awaiting_note_for")
        note_text = update.message.text
        user_id = self.get_user_id(update)
        user_name = get_employee_name(user_id)
        user_role = get_user_role(user_id)

        db = await self._get_db()
        try:
            success = NoteService.add_note(
                db=db,
                job_id=job_id,
                user_id=user_id,
                user_name=user_name,
                user_role=user_role,
                note=note_text
            )

            if success:
                await Helpers.safe_edit_text(
                    update.effective_message,
                    MessageTemplates.format_success_message("Note added successfully!"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to Job", callback_data=f"job_menu_{job_id}")]
                    ])
                )
                await self.view_job(update, context, job_id)
            else:
                await update.message.reply_text("⚠️ Failed to save note. Please try again.")
        finally:
            db.close()
    async def view_job_with_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int):
        """View job with all notes"""
        db = await self._get_db()
        ground = await self.ground_service.get_ground(db, job_id)
        notes = NoteService.get_notes_for_job(db, job_id)
        
        # Format job details
        job_card = MessageTemplates.format_job_card(
            site_name=ground.site_name,
            status=ground.status,
            area=ground.area,
            duration=ground.duration,
            photo_count=ground.photo_count
        )
        
        # Format notes section
        notes_section = "📝 JOB NOTES:\n" + MessageTemplates.SEPARATOR
        if notes:
            for note in notes:
                notes_section += f"\n👤 {note['author']} at {note['created_at']}:\n"
                notes_section += f"{note['note']}\n"
                if note['has_photo']:
                    notes_section += "📸 (Photo attached)\n"
                notes_section += MessageTemplates.SEPARATOR
        else:
            notes_section += "\nNo notes yet for this job."

        # Create buttons
        buttons = [
            [InlineKeyboardButton("➕ Add Note", callback_data=f"add_note_{job_id}")],
            [InlineKeyboardButton("📸 Add Photo Note", callback_data=f"add_photo_note_{job_id}")],
            [InlineKeyboardButton("🔙 Back to Job", callback_data=f"job_menu_{job_id}")]
        ]
        
        await self._send_message(
            update,
            f"{job_card}\n\n{notes_section}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )  # This was the missing closing parenthesis
        
    async def prepare_add_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prepare context for note addition"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        context.user_data["awaiting_note_for"] = job_id
        context.user_data["note_type"] = "text"
        
        await self._send_message(
            update,
            "✏️ Please type your note for this job:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data=f"view_notes_{job_id}")]
            ])
        )
    
    async def prepare_add_photo_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prepare context for photo note addition"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        context.user_data["awaiting_note_for"] = job_id
        context.user_data["note_type"] = "photo"
        
        await self._send_message(
            update,
            "📸 Please send a photo with optional caption for this job:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data=f"view_notes_{job_id}")]
            ])
        )
    
    async def handle_note_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle both text and photo notes"""
        if "awaiting_note_for" not in context.user_data:
            return
            
        job_id = context.user_data.pop("awaiting_note_for")
        note_type = context.user_data.pop("note_type", "text")
        user_id = self.get_user_id(update)
        user_name = get_employee_name(user_id)
        user_role = get_user_role(user_id)
        db = await self._get_db()
        
        if note_type == "text":
            note_text = update.message.text
            NoteService.add_note(db, job_id, user_id, user_name, user_role, note_text)
            confirmation = "📝 Text note added successfully!"
        else:
            # Handle photo note
            photo_file = await update.message.photo[-1].get_file()
            photo_path = f"photos/note_{job_id}_{datetime.now().timestamp()}.jpg"
            await photo_file.download_to_drive(photo_path)
            
            note_text = update.message.caption or "Photo note"
            NoteService.add_note(
                db, job_id, user_id, user_name, user_role, 
                note_text, photo_path
            )
            confirmation = "📸 Photo note added successfully!"
        
        await self._send_message(
            update,
            MessageTemplates.format_success_message(confirmation),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View All Notes", callback_data=f"view_notes_{job_id}")]
            ])
        )
    async def start_job_with_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a job and prepare for note-taking"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        
        # Start the job
        success, message = await self.ground_service.start_job(db, job_id)
        if not success:
            await self._send_message(update, message)
            return

        # Prepare context for notes
        context.user_data["current_job"] = job_id
        context.user_data["note_mode"] = True

        # Send confirmation with note options
        buttons = [
            [InlineKeyboardButton("📝 Add Work Note", callback_data=f"add_work_note_{job_id}")],
            [InlineKeyboardButton("📸 Add Photo Note", callback_data=f"add_photo_note_{job_id}")],
            [InlineKeyboardButton("✅ Finish Job", callback_data=f"finish_job_{job_id}")]
        ]
        
        await self._send_message(
            update,
            "🛠️ Job started! You can now add notes as you work:\n"
            "1. Use 'Add Work Note' for text updates\n"
            "2. Use 'Add Photo Note' for photo documentation\n"
            "3. Finish when complete",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    async def add_work_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prepare to receive a work note"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        context.user_data["awaiting_work_note"] = job_id
        
        await self._send_message(
            update,
            "✏️ Please enter your work note (what you're doing, issues found, etc.):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data=f"job_working_{job_id}")]
            ])
        )
    async def handle_work_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process a submitted work note"""
        if "awaiting_work_note" not in context.user_data:
            return

        job_id = context.user_data.pop("awaiting_work_note")
        note_text = update.message.text
        user_id = self.get_user_id(update)
        user_name = get_employee_name(user_id)
        user_role = get_user_role(user_id)
        
        db = await self._get_db()
        NoteService.add_note(
            db, 
            job_id, 
            user_id, 
            user_name, 
            user_role, 
            f"Work Update: {note_text}"
        )
        
        # Return to job working view
        await self._send_message(
            update,
            MessageTemplates.format_success_message("Work note added!"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Back to Job", callback_data=f"job_working_{job_id}")]
            ])
        )
    async def job_working_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the job working interface with notes"""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        ground = await self.ground_service.get_ground(db, job_id)
        notes = NoteService.get_notes_for_job(db, job_id)

        # Get only work-related notes
        work_notes = [n for n in notes if "Work Update:" in n['note']]
        
        message = (
            f"🛠️ Working on: {ground.site_name}\n"
            f"⏱️ Time working: {ground.duration or 'Just started'}\n\n"
            f"📝 Recent Work Notes:\n{MessageTemplates.SEPARATOR}\n"
        )
        
        if work_notes:
            for note in work_notes[:3]:  # Show most recent 3 notes
                message += f"\n{note['created_at']}: {note['note']}\n"
                message += MessageTemplates.SEPARATOR
        else:
            message += "\nNo work notes yet\n"
            message += MessageTemplates.SEPARATOR

        buttons = [
            [InlineKeyboardButton("📝 Add Work Note", callback_data=f"add_work_note_{job_id}"),
            InlineKeyboardButton("📸 Add Photo Note", callback_data=f"add_photo_note_{job_id}")],
            [InlineKeyboardButton("✅ Finish Job", callback_data=f"finish_job_{job_id}")]
        ]
        
        await self._send_message(update, message, reply_markup=InlineKeyboardMarkup(buttons))

