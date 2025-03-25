#!/usr/bin/env python
######################################################
# TELEGRAM_BOT.PY (ULTIMATE VERSION V8 - ENHANCED MowBot MVP)
#
# Features:
# - Enhanced UI Components: Professional message templates and button layouts
# - Photo Upload Enhancement: Splits media groups into chunks of 10 (up to 25 photos)
# - Director Dashboard:
#    • View unassigned jobs (labeled "Assign Jobs") in pages (neatly formatted)
#    • Tick/untick (select/unselect) jobs for assignment
#    • Assign selected jobs to Andy or Alex and select a day of the week
#    • View completed jobs and job details (photos, data)
# - Employee Dashboard:
#    • View daily jobs with inline buttons for start/finish, site info, map link, and upload photos
#    • All actions update the same message (smooth inline editing)
# - Dev Dashboard for debugging access (redirects to the director's assign jobs view)
#
# All inline actions use update.effective_message for smooth UX.
######################################################

import os
import logging
import sqlite3
from datetime import datetime, timedelta
import asyncio
from PIL import Image
import io
import pytz
import time
import threading
import sys

# Import telegram modules (using lowercase filters for PTB v20+)
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters
)
from telegram.error import BadRequest

# Custom modules – ensure these work as expected.
from src.bot.utils.message_templates import MessageTemplates
from src.bot.utils.button_layouts import ButtonLayouts
from src.bot.database.models import get_db, Ground
from src.bot.services.ground_service import GroundService
from src.bot.utils.decorators import error_handler, director_only, employee_required

#####################
# ENV & TOKEN SETUP
#####################

from dotenv import load_dotenv
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global dictionary for simulation user data (if needed)
user_data = {}

# Async helper function for safe inline editing using update.effective_message.
async def safe_edit_text(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None):
    try:
        await update.effective_message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(text, reply_markup=reply_markup)

#####################
# ROLES & USERS
#####################

dev_users = {1672989849}
director_users = {1672989849, 7996550019, 8018680694}
employee_users = {1672989849: "Andy", 6396234665: "Alex"}

def get_user_role(user_id: int) -> str:
    if user_id in dev_users:
        return "Dev"
    elif user_id in director_users:
        return "Director"
    elif user_id in employee_users:
        return "Employee"
    return "Generic"

#####################
# DATABASE SETUP
#####################

conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript(
    """
    CREATE TABLE IF NOT EXISTS grounds_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_name TEXT UNIQUE,
        quote TEXT,
        address TEXT,
        order_no TEXT,
        order_period TEXT,
        area TEXT,
        summer_schedule TEXT,
        winter_schedule TEXT,
        contact TEXT,
        gate_code TEXT,
        map_link TEXT,
        assigned_to INTEGER,
        status TEXT DEFAULT 'pending',
        photos TEXT,
        start_time TIMESTAMP,
        finish_time TIMESTAMP,
        notes TEXT,
        scheduled_date TEXT,
        priority TEXT DEFAULT 'normal'
    );
    """
)

cursor.executescript(""" 
    CREATE INDEX IF NOT EXISTS idx_grounds_assigned_to ON grounds_data(assigned_to);
    CREATE INDEX IF NOT EXISTS idx_grounds_status ON grounds_data(status);
    CREATE INDEX IF NOT EXISTS idx_grounds_site_name ON grounds_data(site_name);
""")

try:
    cursor.execute("ALTER TABLE grounds_data ADD COLUMN scheduled_date TEXT;")
    cursor.execute("ALTER TABLE grounds_data ADD COLUMN priority TEXT DEFAULT 'normal';")
    conn.commit()
    logger.info("Added new columns to grounds_data.")
except sqlite3.OperationalError as e:
    logger.info("New columns likely already exist.")

#######################################
# HANDLERS (All handlers are async)
#######################################

async def handle_photo(update: Update, context: CallbackContext):
    if "awaiting_photo_for" not in context.user_data:
        await update.message.reply_text("No photo expected at this time.")
        return
    job_id = context.user_data["awaiting_photo_for"]
    photo_file = await update.message.photo[-1].get_file()
    photo_dir = "photos"
    os.makedirs(photo_dir, exist_ok=True)
    photo_filename = f"job_{job_id}_{photo_file.file_id}.jpg"
    photo_path = os.path.join(photo_dir, photo_filename)
    try:
        photo_bytes = await photo_file.download_as_bytearray()
        with Image.open(io.BytesIO(photo_bytes)) as img:
            img.verify()
            img.save(photo_path, format='JPEG')
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await update.message.reply_text(MessageTemplates.format_error_message("Photo Error", "Failed to process the photo.", "PHOTO_ERROR"))
        return
    try:
        cursor.execute("SELECT photos FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        current = result[0] if result else ""
        new_photos = current.strip() + "|" + photo_path if current and current.strip() else photo_path
        current_count = len(current.split("|")) if current and current.strip() else 0
        if current_count >= 25:
            await update.message.reply_text(MessageTemplates.format_error_message("Photo Limit Reached", "Maximum number of photos reached for this job.", "PHOTO_LIMIT"))
            return
        cursor.execute("UPDATE grounds_data SET photos = ? WHERE id = ?", (new_photos, job_id))
        conn.commit()
        photo_count = len(new_photos.split("|"))
        confirmation_text = MessageTemplates.format_success_message("Photo uploaded", f"Photo uploaded for Job {job_id}. ({photo_count}/25 photos uploaded)")
        keyboard = [
            [InlineKeyboardButton("📸 View Photos", callback_data=f"view_photos_{job_id}")],
            [InlineKeyboardButton("📝 Continue Uploading", callback_data=f"upload_photo_{job_id}")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(confirmation_text, reply_markup=markup)
    except sqlite3.Error as e:
        logger.error(f"Database error while saving photo: {e}")
        await update.message.reply_text(MessageTemplates.format_error_message("Database Error", "Failed to save photo.", "DB_ERROR"))

async def handle_text(update: Update, context: CallbackContext):
    if "awaiting_note_for" in context.user_data:
        job_id = context.user_data.pop("awaiting_note_for")
        note = update.message.text
        try:
            cursor.execute("SELECT site_name FROM grounds_data WHERE id = ?", (job_id,))
            result = cursor.fetchone()
            if not result:
                await update.message.reply_text(MessageTemplates.format_error_message("Job not found", "The job you requested was not found.", "JOB_404"))
                return
            site_name = result[0]
            cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (note, job_id))
            conn.commit()
            keyboard = [
                [InlineKeyboardButton("👀 View Job", callback_data=f"view_job_{job_id}")],
                [InlineKeyboardButton("📝 Edit Again", callback_data=f"edit_note_{job_id}")]
            ]
            markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(MessageTemplates.format_success_message("Note Updated", f"Note updated for {site_name} (Job {job_id})."), reply_markup=markup)
        except sqlite3.Error as e:
            logger.error(f"Database error while updating note: {e}")
            await update.message.reply_text(MessageTemplates.format_error_message("Database Error", "Failed to update note.", "DB_ERROR"))
        return
    if "awaiting_notes" in context.user_data and context.user_data["awaiting_notes"]:
        notes = update.message.text
        selected_jobs = context.user_data.get("selected_jobs", set())
        try:
            updated_count = 0
            for site_name in selected_jobs:
                cursor.execute("SELECT id FROM grounds_data WHERE site_name = ?", (site_name,))
                job = cursor.fetchone()
                if job:
                    cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (notes, job[0]))
                    updated_count += 1
            conn.commit()
            del context.user_data["awaiting_notes"]
            await update.message.reply_text(MessageTemplates.format_success_message("Notes Added", f"Notes added to {updated_count} job(s)."))
            await director_assign_jobs(update, context)
        except sqlite3.Error as e:
            logger.error(f"Database error while adding notes: {e}")
            await update.message.reply_text(MessageTemplates.format_error_message("Database Error", "Failed to add notes.", "DB_ERROR"))

async def handle_toggle_job(update: Update, context: CallbackContext):
    data = update.callback_query.data
    job_id = int(data.split("_")[-1])
    try:
        selected_jobs = context.user_data.get("selected_jobs", set())
        if job_id in selected_jobs:
            selected_jobs.remove(job_id)
        else:
            selected_jobs.add(job_id)
        context.user_data["selected_jobs"] = selected_jobs
        current_page = context.user_data.get("current_page", 1)
        text, markup = await build_director_assign_jobs_page(current_page, context)
        await safe_edit_text(update, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error toggling job selection: {e}")
        await update.callback_query.answer("Error toggling job selection. Please try again.", show_alert=True)

async def format_job_section(section_title: str, jobs: list) -> list:
    status_emoji = MessageTemplates.STATUS_EMOJIS.get(jobs[0][5].lower(), '❓')
    sections = [f"\n{status_emoji} {section_title} Jobs:"]
    for job in jobs:
        job_id, site_name, scheduled_date, start_time, finish_time, status, area, notes = job
        duration_str = "N/A"
        if start_time and finish_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                finish_dt = datetime.fromisoformat(finish_time)
                duration_str = str(finish_dt - start_dt).split('.')[0]
            except Exception:
                duration_str = "N/A"
        sections.append(MessageTemplates.format_job_card(site_name=site_name, status=status, area=area, duration=duration_str, notes=notes))
    return sections

async def create_job_buttons(jobs: list) -> list:
    buttons = []
    for job in jobs:
        job_id, site_name, scheduled_date, start_time, finish_time, status, area, _ = job
        status_emoji = MessageTemplates.STATUS_EMOJIS.get(status.lower(), '❓')
        duration = ""
        if start_time and finish_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                finish_dt = datetime.fromisoformat(finish_time)
                duration = f" ({str(finish_dt - start_dt).split('.')[0]})"
            except Exception:
                pass
        buttons.append([InlineKeyboardButton(f"{status_emoji} {site_name}{duration}", callback_data=f"view_job_{job_id}")])
    return buttons

async def build_director_assign_jobs_page(page: int, context: CallbackContext) -> tuple:
    jobs_per_page = 5
    cursor.execute(
        """
        SELECT id, site_name, area, status 
        FROM grounds_data 
        WHERE assigned_to IS NULL 
        ORDER BY id
        """, (jobs_per_page, page * jobs_per_page)
    )
    jobs = cursor.fetchall()
    if not jobs:
        return (
            MessageTemplates.format_success_message("No Jobs Available", "There are no unassigned jobs available."),
            InlineKeyboardMarkup([[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]])
        )
    selected_jobs = context.user_data.get("selected_jobs", set())
    text_parts = [MessageTemplates.format_job_list_header("Available Jobs", len(jobs))]
    for job_id, site_name, area, status in jobs:
        is_selected = site_name in selected_jobs
        status_emoji = MessageTemplates.STATUS_EMOJIS.get(status.lower(), '❓')
        text_parts.append(f"{'✅' if is_selected else '⬜️'} {status_emoji} {site_name} ({area or 'No Area'})")
    keyboard = []
    for job_id, site_name, area, status in jobs:
        is_selected = site_name in selected_jobs
        keyboard.append([InlineKeyboardButton(f"{'✅' if is_selected else '⬜️'} {site_name}", callback_data=f"toggle_job_{site_name}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard"))
    if len(jobs) == jobs_per_page:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    keyboard.append(nav_buttons)
    if selected_jobs:
        keyboard.append([InlineKeyboardButton("📝 Add Notes", callback_data="add_notes"),
                         InlineKeyboardButton("✅ Assign Selected", callback_data="assign_selected_jobs")])
    return "\n\n".join(text_parts), InlineKeyboardMarkup(keyboard)

async def view_job_photos(update: Update, context: CallbackContext):
    query = update.callback_query
    job_id = query.data.split('_')[2]
    cursor.execute("SELECT photos FROM grounds_data WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    if not result or not result[0]:
        await query.answer("No photos available for this job.")
        return
    photo_paths = result[0].split('|')
    media_group = []
    for path in photo_paths:
        try:
            with open(path.strip(), 'rb') as photo:
                media_group.append(InputMediaPhoto(media=photo))
        except Exception as e:
            logger.error(f"Error loading photo {path}: {e}")
            continue
    if not media_group:
        await query.answer("Error loading photos. Please try again.")
        return
    try:
        await context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group, caption=f"Photos for job #{job_id}")
        await query.answer()
    except Exception as e:
        logger.error(f"Error sending photos: {e}")
        await query.answer("Error sending photos. Please try again.")

async def director_view_employee_jobs(update: Update, context: CallbackContext, employee_id: int, employee_name: str):
    cursor.execute(
        """
        SELECT id, site_name, scheduled_date, start_time, finish_time, status, area, notes 
        FROM grounds_data 
        WHERE assigned_to = ? AND (scheduled_date IS NULL OR DATE(scheduled_date) = DATE('now','localtime'))
        ORDER BY scheduled_date, id
        """, (employee_id,)
    )
    jobs = cursor.fetchall()
    if not jobs:
        await safe_edit_text(update, MessageTemplates.format_success_message("No Jobs", f"No jobs assigned to {employee_name} today."))
        return
    sections = [MessageTemplates.format_job_list_header(f"{employee_name}'s Jobs", len(jobs))]
    active_jobs = [j for j in jobs if j[5] == 'in_progress']
    pending_jobs = [j for j in jobs if j[5] == 'pending']
    completed_jobs = [j for j in jobs if j[5] == 'completed']
    if active_jobs:
        sections.extend(await format_job_section("Active", active_jobs))
    if pending_jobs:
        sections.extend(await format_job_section("Pending", pending_jobs))
    if completed_jobs:
        sections.extend(await format_job_section("Completed", completed_jobs))
    buttons = await create_job_buttons(jobs)
    buttons.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    await safe_edit_text(update, "\n\n".join(sections), reply_markup=InlineKeyboardMarkup(buttons))

async def director_view_andys_jobs(update: Update, context: CallbackContext):
    await director_view_employee_jobs(update, context, 1672989849, "Andy")

async def director_view_alexs_jobs(update: Update, context: CallbackContext):
    await director_view_employee_jobs(update, context, 6396234665, "Alex")

#######################################
# DEV FUNCTIONS
#######################################

async def dev_dashboard(update: Update, context: CallbackContext):
    # For dev, simply show the director's "Assign Jobs" view.
    await director_dashboard(update, context)

async def dev_director_dashboard(update: Update, context: CallbackContext):
    await director_dashboard(update, context)

async def dev_employee_dashboard(update: Update, context: CallbackContext):
    await emp_employee_dashboard(update, context)

#######################################
# DIRECTOR FUNCTIONS
#######################################

async def director_send_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        """
        SELECT site_name, photos, start_time, finish_time, notes, contact, gate_code, map_link, area 
        FROM grounds_data 
        WHERE id = ?
        """, (job_id,)
    )
    row = cursor.fetchone()
    if not row:
        await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
        return
    site_name, photos, start_time, finish_time, notes, contact, gate_code, map_link, area = row
    duration_str = "N/A"
    if start_time and finish_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            finish_dt = datetime.fromisoformat(finish_time)
            duration_str = str(finish_dt - start_dt).split('.')[0]
        except Exception:
            duration_str = "N/A"
    sections = [MessageTemplates.format_job_card(site_name=site_name, status="completed" if finish_dt else "in_progress", area=area, duration=duration_str, notes=notes)]
    if contact or gate_code:
        sections.append(MessageTemplates.format_site_info(site_name=site_name, contact=contact, gate_code=gate_code, address=None, special_instructions=None))
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]]
    markup = InlineKeyboardMarkup(keyboard)
    if photos:
        photos_list = photos.strip().split("|") if photos and photos.strip() else []
        media_group = []
        for p in photos_list:
            abs_path = os.path.join(os.getcwd(), p.strip())
            if os.path.exists(abs_path):
                try:
                    media_group.append(InputMediaPhoto(media=open(abs_path, 'rb')))
                except Exception as e:
                    logger.error(f"Error preparing photo for job {job_id}: {e}")
            else:
                logger.warning(f"Photo file not found: {abs_path}")
        if media_group:
            max_items = 10
            chunks = [media_group[i:i + max_items] for i in range(0, len(media_group), max_items)]
            for index, chunk in enumerate(chunks):
                if index == 0:
                    if len(chunk) == 1:
                        try:
                            await update.effective_message.reply_photo(photo=chunk[0].media, caption="\n\n".join(sections), reply_markup=markup)
                        except Exception as e:
                            logger.error(f"Error sending photo: {e}")
                    else:
                        try:
                            await update.effective_message.reply_media_group(media=chunk)
                            await update.effective_message.reply_text("\n\n".join(sections), reply_markup=markup)
                        except Exception as e:
                            logger.error(f"Error sending media group: {e}")
                else:
                    try:
                        await update.effective_message.reply_media_group(media=chunk)
                    except Exception as e:
                        logger.error(f"Error sending additional media group: {e}")
        else:
            await safe_edit_text(update, "\n\n".join(sections), reply_markup=markup)
    else:
        await safe_edit_text(update, "\n\n".join(sections), reply_markup=markup)

async def director_select_day_for_assignment(update: Update, context: CallbackContext):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    keyboard = [[InlineKeyboardButton(day, callback_data=f"assign_day_{day}")] for day in days]
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    current_hour = datetime.now().hour
    greeting = "Good Morning" if current_hour < 12 else "Good Afternoon"
    header = f"{greeting}! Please select a day for assignment:"
    await safe_edit_text(update, header, reply_markup=markup)

async def director_assign_day_selected(update: Update, context: CallbackContext):
    selected_day = update.callback_query.data.split("_")[-1]
    context.user_data["selected_day"] = selected_day
    keyboard = []
    for emp_id, emp_name in employee_users.items():
        keyboard.append([InlineKeyboardButton(f"Assign to {emp_name}", callback_data=f"assign_to_{emp_id}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    message = MessageTemplates.format_success_message("Day Selected", f"You selected {selected_day}. Please choose an employee to assign the selected jobs.")
    await safe_edit_text(update, message, reply_markup=markup)

async def director_dashboard(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    name = employee_users.get(user_id, "Director")
    header = MessageTemplates.format_dashboard_header(name, "Director")
    total_jobs = len(cursor.execute("SELECT id FROM grounds_data").fetchall())
    active_jobs = len(cursor.execute("SELECT id FROM grounds_data WHERE status = 'in_progress'").fetchall())
    completed_jobs = len(cursor.execute("SELECT id FROM grounds_data WHERE status = 'completed'").fetchall())
    stats = [
        f"📊 Today's Overview:",
        f"• Total Jobs: {total_jobs}",
        f"• Active: {active_jobs}",
        f"• Completed: {completed_jobs}",
        MessageTemplates.SEPARATOR
    ]
    message_text = f"{header}\n\n" + "\n".join(stats)
    # Updated inline keyboard: "Assign Jobs" button (shows unassigned jobs)
    director_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Assign Jobs", callback_data="dir_assign_jobs")],
        [InlineKeyboardButton("View Completed Jobs", callback_data="calendar_view")]
    ])
    await safe_edit_text(update, message_text, reply_markup=director_kb)

async def director_add_notes(update: Update, context: CallbackContext):
    if "selected_jobs" not in context.user_data or not context.user_data["selected_jobs"]:
        await safe_edit_text(update, MessageTemplates.format_error_message("No Jobs Selected", "Please select jobs before adding notes.", "NO_JOBS_SELECTED"))
        return
    context.user_data["awaiting_notes"] = True
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data="director_dashboard")]]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, MessageTemplates.format_input_prompt("Please send the notes to add to the selected jobs:"), reply_markup=markup)

async def director_edit_note(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT site_name FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
            return
        site_name = result[0]
        context.user_data["awaiting_note_for"] = job_id
        keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data=f"cancel_note_{job_id}")]]
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_text(update, MessageTemplates.format_input_prompt(f"Please send the note for {site_name} (Job {job_id}):"), reply_markup=markup)
    except sqlite3.Error as e:
        logger.error(f"Database error while preparing note edit: {e}")
        await safe_edit_text(update, MessageTemplates.format_error_message("Database Error", "Failed to prepare note editing. Please try again.", "DB_ERROR"))

async def director_cancel_note(update: Update, context: CallbackContext):
    await director_send_job(update, context)

async def director_assign_jobs(update: Update, context: CallbackContext):
    if "selected_jobs" not in context.user_data or not context.user_data["selected_jobs"]:
        await safe_edit_text(update, MessageTemplates.format_error_message("No Jobs Selected", "Please select jobs before assigning.", "NO_JOBS_SELECTED"))
        return
    if "selected_day" in context.user_data:
        del context.user_data["selected_day"]
    if "awaiting_notes" in context.user_data:
        del context.user_data["awaiting_notes"]
    keyboard = []
    for emp_id, emp_name in employee_users.items():
        keyboard.append([InlineKeyboardButton(f"Assign to {emp_name}", callback_data=f"assign_to_{emp_id}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    message = MessageTemplates.format_success_message("Select Employee", "Please choose an employee to assign the selected jobs.")
    await safe_edit_text(update, message, reply_markup=markup)

async def assign_jobs_to_employee(update: Update, context: CallbackContext):
    employee_id = int(update.callback_query.data.split("_")[-1])
    selected_jobs = context.user_data.get("selected_jobs", set())
    selected_day = context.user_data.get("selected_day")
    if not selected_jobs:
        await safe_edit_text(update, MessageTemplates.format_error_message("No Jobs Selected", "Please select jobs before assigning.", "NO_JOBS_SELECTED"))
        return
    if not selected_day:
        await director_select_day_for_assignment(update, context)
        return
    try:
        for site_name in selected_jobs:
            cursor.execute("UPDATE grounds_data SET assigned_to = ?, scheduled_date = ? WHERE site_name = ?", (employee_id, selected_day, site_name))
        conn.commit()
        message = MessageTemplates.format_success_message("Jobs Assigned", f"Selected jobs have been assigned to {employee_users.get(employee_id, 'Employee')} for {selected_day}.")
        await safe_edit_text(update, message)
        if "selected_jobs" in context.user_data:
            del context.user_data["selected_jobs"]
        if "selected_day" in context.user_data:
            del context.user_data["selected_day"]
        await director_dashboard(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while assigning jobs: {e}")
        await safe_edit_text(update, MessageTemplates.format_error_message("Database Error", "Failed to assign jobs. Please try again.", "DB_ERROR"))

async def director_calendar_view(update: Update, context: CallbackContext):
    text = MessageTemplates.format_success_message("Calendar View", "Calendar View: [Feature coming soon - This is a stub]")
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, text, reply_markup=markup)

#######################################
# EMPLOYEE FUNCTIONS
#######################################

async def emp_employee_dashboard(update: Update, context: CallbackContext):
    if "awaiting_photo_for" in context.user_data:
        del context.user_data["awaiting_photo_for"]
    back_callback = "dev_dashboard" if update.effective_user.id in dev_users else "start"
    keyboard = [
        [InlineKeyboardButton("📋 View My Jobs", callback_data="emp_view_jobs")],
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=back_callback)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = MessageTemplates.format_dashboard_header(employee_users.get(update.effective_user.id, "Employee"), "Employee")
    await safe_edit_text(update, text, reply_markup=markup)

async def emp_view_jobs(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute(
        """
        SELECT id, site_name, area, status, notes, start_time, finish_time 
        FROM grounds_data 
        WHERE assigned_to = ? AND (start_time IS NULL OR DATE(start_time) = DATE('now', 'localtime'))
        """, (user_id,)
    )
    jobs = cursor.fetchall()
    if not jobs:
        message = MessageTemplates.format_success_message("No Jobs", "You have no assigned jobs today.")
        await safe_edit_text(update, message)
        return
    keyboard = []
    for job_id, site_name, area, status, notes, start_time, finish_time in jobs:
        prefix = MessageTemplates.STATUS_EMOJIS.get(status.lower(), '❓')
        duration = ""
        if start_time and finish_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                finish_dt = datetime.fromisoformat(finish_time)
                duration = f" ({str(finish_dt - start_dt).split('.')[0]})"
            except Exception:
                pass
        keyboard.append([InlineKeyboardButton(f"{prefix}{site_name} ({area or 'No Area'}) [{status.capitalize()}]{duration}", callback_data=f"job_menu_{job_id}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="emp_employee_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    message = MessageTemplates.format_job_list_header("Your Jobs (Today)", len(jobs))
    await safe_edit_text(update, message, reply_markup=markup)

async def emp_job_menu(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        """
        SELECT site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link, photos 
        FROM grounds_data 
        WHERE id = ?
        """, (job_id,)
    )
    job_data = cursor.fetchone()
    if not job_data:
        await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
        return
    site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link, photos = job_data
    sections = [MessageTemplates.format_job_card(site_name=site_name, status=status, area=area,
                duration=(str(datetime.fromisoformat(finish_time) - datetime.fromisoformat(start_time)).split('.')[0] if start_time and finish_time else "N/A"),
                notes=notes)]
    if contact or gate_code:
        sections.append(MessageTemplates.format_site_info(site_name=site_name, contact=contact, gate_code=gate_code, address=None, special_instructions=None))
    keyboard = []
    if status == 'pending':
        keyboard.append([InlineKeyboardButton("▶️ Start Job", callback_data=f"start_job_{job_id}")])
    elif status == 'in_progress':
        keyboard.append([InlineKeyboardButton("✅ Finish Job", callback_data=f"finish_job_{job_id}")])
    keyboard.append([InlineKeyboardButton("📸 Upload Photo", callback_data=f"upload_photo_{job_id}")])
    if contact or gate_code:
        keyboard.append([InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}")])
    if map_link:
        keyboard.append([InlineKeyboardButton("🗺 Map Link", callback_data=f"map_link_{job_id}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="emp_view_jobs")])
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, "\n\n".join(sections), reply_markup=markup)

async def emp_start_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT status FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
            return
        current_status = result[0]
        if current_status == 'in_progress':
            await safe_edit_text(update, MessageTemplates.format_error_message("Already Started", "This job is already in progress.", "JOB_IN_PROGRESS"))
            return
        cursor.execute("UPDATE grounds_data SET status = 'in_progress', start_time = ? WHERE id = ?", (datetime.now().isoformat(), job_id))
        conn.commit()
        await safe_edit_text(update, MessageTemplates.format_success_message("Job Started", f"Job {job_id} has been started."))
        await emp_view_jobs(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while starting job: {e}")
        await safe_edit_text(update, MessageTemplates.format_error_message("Database Error", "Failed to start job. Please try again.", "DB_ERROR"))

async def emp_finish_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT status FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
            return
        current_status = result[0]
        if current_status == 'completed':
            await safe_edit_text(update, MessageTemplates.format_error_message("Already Completed", "This job is already completed.", "JOB_COMPLETED"))
            return
        if current_status != 'in_progress':
            await safe_edit_text(update, MessageTemplates.format_error_message("Not Started", "This job has not been started yet.", "JOB_NOT_STARTED"))
            return
        cursor.execute("UPDATE grounds_data SET status = 'completed', finish_time = ? WHERE id = ?", (datetime.now().isoformat(), job_id))
        conn.commit()
        await safe_edit_text(update, MessageTemplates.format_success_message("Job Completed", f"Job {job_id} has been completed."))
        await emp_view_jobs(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while finishing job: {e}")
        await safe_edit_text(update, MessageTemplates.format_error_message("Database Error", "Failed to complete job. Please try again.", "DB_ERROR"))

async def emp_upload_photo(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["awaiting_photo_for"] = job_id
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data=f"job_menu_{job_id}")]]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, MessageTemplates.format_input_prompt("Please send the photo for this job:"), reply_markup=markup)

async def emp_site_info(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, contact, gate_code, address FROM grounds_data WHERE id = ?", (job_id,))
    job_data = cursor.fetchone()
    if not job_data:
        await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
        return
    site_name, contact, gate_code, address = job_data
    info_text = MessageTemplates.format_site_info(site_name=site_name, contact=contact, gate_code=gate_code, address=address, special_instructions=None)
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=f"job_menu_{job_id}")]]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, info_text, reply_markup=markup)

async def emp_map_link(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, map_link FROM grounds_data WHERE id = ?", (job_id,))
    job_data = cursor.fetchone()
    if not job_data:
        await safe_edit_text(update, MessageTemplates.format_error_message("Job not found", "The requested job was not found.", "JOB_404"))
        return
    site_name, map_link = job_data
    if not map_link:
        await safe_edit_text(update, MessageTemplates.format_error_message("No Map Link", "No map link available for this job.", "NO_MAP_LINK"))
        return
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=f"job_menu_{job_id}")]]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update, f"🗺 Map Link for {site_name}:\n{map_link}", reply_markup=markup)

#######################################
# CALLBACK QUERY HANDLER
#######################################

async def callback_handler(update: Update, context: CallbackContext):
    data = update.callback_query.data
    await update.callback_query.answer()
    handlers = {
        "start": start,
        "dev_employee_dashboard": dev_employee_dashboard,
        "dev_director_dashboard": dev_director_dashboard,
        "view_andys_jobs": director_view_andys_jobs,
        "view_alexs_jobs": director_view_alexs_jobs,
        "calendar_view": director_calendar_view,
        "director_dashboard": director_dashboard,
        "emp_view_jobs": emp_view_jobs,
        "emp_employee_dashboard": emp_employee_dashboard,
        "add_notes": director_add_notes,
        "dir_assign_jobs": director_assign_jobs,
        "assign_selected_jobs": director_select_day_for_assignment
    }
    if data in handlers:
        await handlers[data](update, context)
        return
    if data.startswith("select_day_"):
        await director_select_day_for_assignment(update, context)
    elif data.startswith("assign_day_"):
        await director_assign_day_selected(update, context)
    elif data.startswith("dir_assign_jobs_"):
        await director_assign_jobs(update, context)
    elif data.startswith("toggle_job_"):
        await handle_toggle_job(update, context)
    elif data.startswith("assign_to_"):
        await assign_jobs_to_employee(update, context)
    elif data.startswith("job_menu_"):
        await emp_job_menu(update, context)
    elif data.startswith("upload_photo_"):
        await emp_upload_photo(update, context)
    elif data.startswith("site_info_"):
        await emp_site_info(update, context)
    elif data.startswith("start_job_"):
        await emp_start_job(update, context)
    elif data.startswith("finish_job_"):
        await emp_finish_job(update, context)
    elif data.startswith("map_link_"):
        await emp_map_link(update, context)
    elif data.startswith("send_job_"):
        await director_send_job(update, context)
    elif data.startswith("edit_note_"):
        await director_edit_note(update, context)
    elif data.startswith("cancel_note_"):
        await director_cancel_note(update, context)
    elif data.startswith("view_job_"):
        await director_send_job(update, context)
    elif data.startswith("view_photos_"):
        await view_job_photos(update, context)
    elif data.startswith("page_"):
        page = int(data.split("_")[-1])
        context.user_data["current_page"] = page
        text, markup = await build_director_assign_jobs_page(page, context)
        await safe_edit_text(update, text, reply_markup=markup)
    elif data == "noop":
        pass
    else:
        await safe_edit_text(update, MessageTemplates.format_error_message("Unknown Action", "This action is not supported.", "UNKNOWN_ACTION"))

#######################################
# DAILY RESET FUNCTION
#######################################

async def reset_completed_jobs():
    logger.info("Resetting completed jobs for a new day.")
    cursor.execute("UPDATE grounds_data SET status = 'pending', assigned_to = NULL, finish_time = NULL WHERE status = 'completed' AND (scheduled_date IS NULL OR scheduled_date = date('now','localtime'))")
    conn.commit()

#######################################
# START & HELP COMMANDS
#######################################

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    if role == "Dev":
        await dev_dashboard(update, context)
    elif role == "Director":
        await director_dashboard(update, context)
    elif role == "Employee":
        await emp_employee_dashboard(update, context)
    else:
        text = MessageTemplates.format_error_message("Access Denied", "You do not have a registered role.", "ROLE_404")
        if update.callback_query:
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)

async def help_command(update: Update, context: CallbackContext):
    text = (
        "🤖 *Bot Help*\n\n"
        "*/start* - Launch the bot and navigate to your dashboard.\n"
        "*/help* - Show this help message.\n\n"
        "Use the inline buttons to navigate dashboards and manage jobs.\n"
        "- *Director*: Assign jobs, edit job notes, view job details with photos, and view completed jobs.\n"
        "- *Employee*: View your assigned jobs, start/finish jobs, and upload photos.\n"
        "- *Dev*: Access debug dashboards (redirects to the director's assign jobs view).\n\n"
        "If you have any questions, ask your system admin."
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

#######################################
# MAIN FUNCTION & SCHEDULER SETUP
#######################################

def start_profit_thread():
    def accumulate_profit():
        while True:
            time.sleep(3600)  # every hour
            for uid, data in user_data.items():
                data['points'] += data['profit_per_hour']
    profit_thread = threading.Thread(target=accumulate_profit, daemon=True)
    profit_thread.start()

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(callback_handler))
    start_profit_thread()
    application.run_polling()

if __name__ == "__main__":
    main()
