from typing import List, Dict, Optional, Union
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class ButtonLayouts:
    """Professional button layouts for consistent UI."""

    # Button style constants
    PRIMARY_PREFIX = "▫️"    # Primary actions
    SECONDARY_PREFIX = "▪️"  # Secondary actions
    DANGER_PREFIX = "⭕"     # Dangerous actions
    SUCCESS_PREFIX = "✅"    # Success/completion actions
    BACK_PREFIX = "◀️"      # Navigation back
    FORWARD_PREFIX = "▶️"    # Navigation forward
    
    @staticmethod
    def create_job_menu(
        job_id: int,
        status: str,
        has_photos: bool = False,
        has_notes: bool = False
    ) -> InlineKeyboardMarkup:
        """Create an enhanced job menu with context-aware buttons."""
        buttons = []
        
        # Primary action button based on status
        if status == 'pending':
            buttons.append([
                InlineKeyboardButton(
                    f"{ButtonLayouts.PRIMARY_PREFIX} Start Job",
                    callback_data=f"start_job_{job_id}"
                )
            ])
        elif status == 'in_progress':
            buttons.append([
                InlineKeyboardButton(
                    f"{ButtonLayouts.SUCCESS_PREFIX} Complete Job",
                    callback_data=f"finish_job_{job_id}"
                )
            ])
        
        # Media and notes section
        media_buttons = []
        if has_photos:
            media_buttons.append(
                InlineKeyboardButton("🖼️ View Photos", callback_data=f"view_photos_{job_id}")
            )
        media_buttons.append(
            InlineKeyboardButton("📸 Add Photos", callback_data=f"upload_photo_{job_id}")
        )
        buttons.append(media_buttons)
        
        # Notes section
        notes_buttons = []
        if has_notes:
            notes_buttons.append(
                InlineKeyboardButton("📝 View Notes", callback_data=f"view_notes_{job_id}")
            )
        notes_buttons.append(
            InlineKeyboardButton("✏️ Add Note", callback_data=f"edit_note_{job_id}")
        )
        buttons.append(notes_buttons)
        
        # Info section
        buttons.append([
            InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}"),
            InlineKeyboardButton("🗺️ Map", callback_data=f"map_link_{job_id}")
        ])
        
        # Navigation
        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back to Jobs", callback_data="emp_view_jobs")
        ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_director_dashboard(show_stats: bool = True) -> InlineKeyboardMarkup:
        """Create an enhanced director dashboard layout."""
        buttons = [
            # Job Management Section
            [InlineKeyboardButton(f"{ButtonLayouts.PRIMARY_PREFIX} Assign Jobs", callback_data="dir_assign_jobs_0")],
            
            # Employee Overview Section
            [
                InlineKeyboardButton("👤 Andy's Jobs", callback_data="view_andys_jobs"),
                InlineKeyboardButton("👤 Alex's Jobs", callback_data="view_alexs_jobs"),
                InlineKeyboardButton("👤 Tan's Jobs", callback_data="view_tans_jobs")
            ],
            
            # Planning Section
            [InlineKeyboardButton("📅 Calendar View", callback_data="calendar_view")]
        ]
        
        # Optional Statistics Section
        if show_stats:
            buttons.append([
                InlineKeyboardButton("📊 Job Stats", callback_data="job_stats"),
                InlineKeyboardButton("📈 Performance", callback_data="performance_stats")
            ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_employee_dashboard(has_active_jobs: bool = False) -> InlineKeyboardMarkup:
        """Create an enhanced employee dashboard layout."""
        buttons = []
        
        # Active Jobs Section (if any)
        if has_active_jobs:
            buttons.append([
                InlineKeyboardButton(
                    f"{ButtonLayouts.PRIMARY_PREFIX} Current Jobs",
                    callback_data="emp_active_jobs"
                )
            ])
        
        # Standard Options
        buttons.extend([
            [InlineKeyboardButton("📋 All My Jobs", callback_data="emp_view_jobs")],
            [
                InlineKeyboardButton("📱 Quick Access", callback_data="quick_access"),
                InlineKeyboardButton("📊 My Stats", callback_data="emp_stats")
            ]
        ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_photo_menu(
        job_id: int,
        photo_count: int,
        max_photos: int,
        show_delete: bool = False
    ) -> InlineKeyboardMarkup:
        """Create an enhanced photo upload menu."""
        buttons = [
            # Status Display
            [InlineKeyboardButton(
                f"📸 Photos: {photo_count}/{max_photos}",
                callback_data="noop"
            )],
            
            # Photo Actions
            [InlineKeyboardButton(
                f"{ButtonLayouts.PRIMARY_PREFIX} Add More Photos",
                callback_data=f"upload_photo_{job_id}"
            )]
        ]
        
        # View/Delete Options
        if photo_count > 0:
            view_delete = []
            view_delete.append(
                InlineKeyboardButton("🖼️ View All", callback_data=f"view_photos_{job_id}")
            )
            if show_delete:
                view_delete.append(
                    InlineKeyboardButton(
                        f"{ButtonLayouts.DANGER_PREFIX} Delete",
                        callback_data=f"delete_photos_{job_id}"
                    )
                )
            buttons.append(view_delete)
        
        # Navigation
        buttons.append([
            InlineKeyboardButton(
                f"{ButtonLayouts.BACK_PREFIX} Back to Job",
                callback_data=f"job_menu_{job_id}"
            )
        ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_confirmation_menu(
        confirm_data: str,
        cancel_data: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        dangerous: bool = False
    ) -> InlineKeyboardMarkup:
        """Create an enhanced confirmation menu."""
        prefix = ButtonLayouts.DANGER_PREFIX if dangerous else ButtonLayouts.SUCCESS_PREFIX
        buttons = [[
            InlineKeyboardButton(f"{prefix} {confirm_text}", callback_data=confirm_data),
            InlineKeyboardButton(f"{ButtonLayouts.SECONDARY_PREFIX} {cancel_text}", callback_data=cancel_data)
        ]]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_pagination_menu(
        current_page: int,
        total_pages: int,
        base_callback: str,
        show_back: bool = True,
        items_per_page: Optional[int] = None
    ) -> InlineKeyboardMarkup:
        """Create an enhanced pagination menu."""
        buttons = []
        
        # Navigation buttons with page info
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(
                InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX}", callback_data=f"{base_callback}_{current_page-1}")
            )
        
        # Page indicator with optional items per page
        page_info = f"Page {current_page + 1}/{total_pages}"
        if items_per_page:
            page_info += f" ({items_per_page} items)"
        nav_buttons.append(
            InlineKeyboardButton(page_info, callback_data="noop")
        )
        
        if current_page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(f"{ButtonLayouts.FORWARD_PREFIX}", callback_data=f"{base_callback}_{current_page+1}")
            )
        
        buttons.append(nav_buttons)
        
        # Back button
        if show_back:
            buttons.append([
                InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="back")
            ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_day_selector(selected_day: Optional[str] = None) -> InlineKeyboardMarkup:
        """Create an enhanced day selector menu."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        buttons = []
        
        for day in days:
            prefix = "✓ " if day == selected_day else "  "
            buttons.append([
                InlineKeyboardButton(
                    f"{prefix}{day}",
                    callback_data=f"select_day_{day.lower()}"
                )
            ])
        
        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")
        ])
        
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def create_quick_actions_menu(job_id: int) -> InlineKeyboardMarkup:
        """Create a menu for quick actions."""
        buttons = [
            [InlineKeyboardButton("⚡ Quick Start", callback_data=f"quick_start_{job_id}")],
            [InlineKeyboardButton("📸 Quick Photo", callback_data=f"quick_photo_{job_id}")],
            [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=f"job_menu_{job_id}")]
        ]
        return InlineKeyboardMarkup(buttons) 
    @staticmethod
    def create_job_menu(job_id: int, status: str, has_notes: bool = False):
        buttons = []
        
        if status == 'pending':
            buttons.append([
                InlineKeyboardButton("▶️ Start Job", callback_data=f"start_job_{job_id}")
            ])
        elif status == 'in_progress':
            buttons.append([
                InlineKeyboardButton("✅ Finish Job", callback_data=f"finish_job_{job_id}"),
                InlineKeyboardButton("📝 Add Note", callback_data=f"add_note_{job_id}"),
            ])
        
        # Common buttons
        buttons.append([
            InlineKeyboardButton("📸 Upload Photo", callback_data=f"upload_photo_{job_id}"),
            InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}")
        ])
        
        if has_notes:
            buttons.append([
                InlineKeyboardButton("🗒️ View Notes", callback_data=f"view_notes_{job_id}")
            ])
        
        buttons.append([
            InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="emp_view_jobs")
        ])
        
        return InlineKeyboardMarkup(buttons)