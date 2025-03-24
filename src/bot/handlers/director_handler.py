from typing import List, Optional
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..utils.message_templates import MessageTemplates
from ..utils.button_layouts import ButtonLayouts
from ..database.models import get_db, Ground
from ..services.ground_service import GroundService
from ..utils.decorators import error_handler, director_only
from ..config.settings import EMPLOYEE_USERS
from .base_handler import BaseHandler

class DirectorHandler(BaseHandler):
    """Handler for director-related operations."""

    def __init__(self):
        super().__init__()

    @error_handler
    @director_only
    async def view_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display the enhanced director dashboard."""
        user_id = self.get_user_id(update)
        name = EMPLOYEE_USERS.get(user_id, "Director")
        
        # Create dashboard header
        header = MessageTemplates.format_dashboard_header(name, "Director")
        
        # Get quick stats
        db = await self._get_db()
        total_jobs = len(await self.ground_service.get_all_grounds(db))
        active_jobs = len(await self.ground_service.get_grounds_by_status(db, 'in_progress'))
        completed_jobs = len(await self.ground_service.get_grounds_by_status(db, 'completed'))
        
        # Add stats to header
        stats = [
            f"📊 Today's Overview:",
            f"• Total Jobs: {total_jobs}",
            f"• Active: {active_jobs}",
            f"• Completed: {completed_jobs}",
            MessageTemplates.SEPARATOR
        ]
        
        message = f"{header}\n\n" + "\n".join(stats)
        markup = ButtonLayouts.create_director_dashboard(show_stats=True)
        
        await self._send_message(update, message, reply_markup=markup)

    @error_handler
    @director_only
    async def view_employee_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE, employee_id: int):
        """View jobs assigned to a specific employee with enhanced UI."""
        db = await self._get_db()
        grounds = await self.ground_service.get_employee_grounds(db, employee_id)
        employee_name = EMPLOYEE_USERS.get(employee_id, "Unknown Employee")
        
        if not grounds:
            await self._send_message(
                update,
                f"📋 No jobs assigned to {employee_name} today.",
                reply_markup=ButtonLayouts.create_director_dashboard()
            )
            return

        # Group jobs by status
        active_jobs = [g for g in grounds if g.status == 'in_progress']
        pending_jobs = [g for g in grounds if g.status == 'pending']
        completed_jobs = [g for g in grounds if g.status == 'completed']

        # Create message sections
        sections = [
            MessageTemplates.format_job_list_header(f"{employee_name}'s Jobs", len(grounds))
        ]

        # Add job sections with enhanced formatting
        if active_jobs:
            sections.extend(self._format_job_section("Active", active_jobs))
        if pending_jobs:
            sections.extend(self._format_job_section("Pending", pending_jobs))
        if completed_jobs:
            sections.extend(self._format_job_section("Completed", completed_jobs))

        # Create interactive buttons for each job
        buttons = self._create_job_buttons(grounds)
        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")
        ])

        await self._send_message(
            update,
            "\n\n".join(sections),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    def _format_job_section(self, section_title: str, jobs: List[Ground]) -> List[str]:
        """Format a section of jobs with consistent styling."""
        status_emoji = MessageTemplates.STATUS_EMOJIS.get(jobs[0].status.lower(), '❓')
        sections = [f"\n{status_emoji} {section_title} Jobs:"]
        
        for job in jobs:
            sections.append(MessageTemplates.format_job_card(
                site_name=job.site_name,
                status=job.status,
                area=job.area,
                duration=job.duration,
                notes=job.notes,
                photo_count=job.photo_count
            ))
        
        return sections

    def _create_job_buttons(self, jobs: List[Ground]) -> List[List[InlineKeyboardButton]]:
        """Create interactive buttons for jobs with status indicators."""
        buttons = []
        for job in jobs:
            status_emoji = MessageTemplates.STATUS_EMOJIS.get(job.status.lower(), '❓')
            duration = f" ({job.duration})" if job.duration else ""
            buttons.append([
                InlineKeyboardButton(
                    f"{status_emoji} {job.site_name}{duration}",
                    callback_data=f"view_job_{job.id}"
                )
            ])
        return buttons

    @error_handler
    @director_only
    async def assign_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display the enhanced job assignment interface."""
        db = await self._get_db()
        unassigned_jobs = await self.ground_service.get_unassigned_grounds(db)
        
        if not unassigned_jobs:
            await self._send_message(
                update,
                MessageTemplates.format_success_message(
                    "All jobs are assigned",
                    "There are no jobs waiting to be assigned."
                ),
                reply_markup=ButtonLayouts.create_director_dashboard()
            )
            return

        # Get any existing selections from context
        selected_jobs = context.user_data.get("selected_jobs", set())
        
        # Create message with job list
        sections = [
            MessageTemplates.format_job_list_header("Unassigned Jobs", len(unassigned_jobs)),
            "\nSelect jobs to assign:"
        ]

        # Add job entries with selection status
        for job in unassigned_jobs:
            checkbox = "☑️" if job.id in selected_jobs else "⬜"
            sections.append(MessageTemplates.format_job_card(
                site_name=f"{checkbox} {job.site_name}",
                status=job.status,
                area=job.area
            ))

        # Create selection buttons
        buttons = []
        for job in unassigned_jobs:
            buttons.append([
                InlineKeyboardButton(
                    f"{'☑️' if job.id in selected_jobs else '⬜'} {job.site_name}",
                    callback_data=f"toggle_job_{job.id}"
                )
            ])

        # Add action buttons if jobs are selected
        if selected_jobs:
            buttons.append([
                InlineKeyboardButton(
                    f"{ButtonLayouts.PRIMARY_PREFIX} Assign Selected ({len(selected_jobs)})",
                    callback_data="assign_selected_jobs"
                )
            ])

        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")
        ])

        await self._send_message(
            update,
            "\n\n".join(sections),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @error_handler
    @director_only
    async def view_job_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View detailed job information with enhanced UI."""
        job_id = int(self.get_callback_data(update).split('_')[-1])
        db = await self._get_db()
        ground = await self.ground_service.get_ground(db, job_id)
        
        if not ground:
            await self._send_message(
                update,
                MessageTemplates.format_error_message("Job not found", code="JOB_404")
            )
            return

        # Format comprehensive job information
        sections = []
        
        # Basic job information
        sections.append(MessageTemplates.format_job_card(
            site_name=ground.site_name,
            status=ground.status,
            area=ground.area,
            duration=ground.duration,
            notes=ground.notes,
            photo_count=ground.photo_count,
            priority=getattr(ground, 'priority', None)
        ))

        # Site information
        sections.append(MessageTemplates.format_site_info(
            site_name=ground.site_name,
            contact=ground.contact,
            gate_code=ground.gate_code,
            address=ground.address,
            special_instructions=getattr(ground, 'special_instructions', None)
        ))

        # Create context-aware button menu
        markup = ButtonLayouts.create_job_menu(
            job_id=job_id,
            status=ground.status,
            has_photos=bool(ground.photos),
            has_notes=bool(ground.notes)
        )

        await self._send_message(
            update,
            "\n\n".join(sections),
            reply_markup=markup
        ) 