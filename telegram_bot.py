######################################################
# TELEGRAM_BOT.PY (ULTIMATE VERSION V8 - ENHANCED MowBot MVP)
#
# Features:
# - Enhanced UI Components: Professional message templates and button layouts
# - Photo Upload Enhancement: Splits media groups into chunks of 10 (up to 25 photos)
# - Job Assignment Improvements: Day selection and job grouping
# - Inline UI Enhancements: Dynamic greetings, sleek inline menus
# - Editing Assigned Jobs: Director can toggle green tick selections
# - Developer Dashboards: Full dev menus for debugging
# - Core functionalities and robust error handling
#
# Future-proofing for a customizable base model and potential AI integrations.
######################################################

import os
import logging
import sqlite3
from datetime import datetime, timedelta
import asyncio
from PIL import Image
import io
import pytz
import sys

# Custom imghdr implementation
def what(filename, h=None):
    """Determine the type of image contained in a file or byte stream."""
    if h is None:
        with open(filename, 'rb') as f:
            h = f.read(32)
    if not h:
        return None
    if h.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if h.startswith(b'\xff\xd8'):
        return 'jpeg'
    if h.startswith(b'GIF87a') or h.startswith(b'GIF89a'):
        return 'gif'
    return None

# Set up custom imghdr module
sys.modules['imghdr'] = type('imghdr', (), {'what': what})()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters
)
from telegram.error import BadRequest

from src.bot.utils.message_templates import MessageTemplates
from src.bot.utils.button_layouts import ButtonLayouts
from src.bot.database.models import get_db, Ground
from src.bot.services.ground_service import GroundService
from src.bot.utils.decorators import error_handler, director_only, employee_required

#####################
# ENV & TOKEN SETUP
#####################

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Helper function for editing messages safely
def safe_edit_text(message, text, reply_markup=None):
    try:
        message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message: {e}")

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
# HANDLERS
#######################################

def handle_photo(update: Update, context: CallbackContext):
    if "awaiting_photo_for" not in context.user_data:
        return
    
    job_id = context.user_data["awaiting_photo_for"]
    photo_file = update.message.photo[-1].get_file()
    photo_dir = "photos"
    os.makedirs(photo_dir, exist_ok=True)
    photo_filename = f"job_{job_id}_{photo_file.file_id}.jpg"
    photo_path = os.path.join(photo_dir, photo_filename)
    
    try:
        photo_bytes = photo_file.download_as_bytearray()
        with Image.open(io.BytesIO(photo_bytes)) as img:
            img.verify()
            img.save(photo_path, format='JPEG')
    except Exception as e:
        logger.error(f"Error processing photo: {str(e)}")
        update.message.reply_text(
            MessageTemplates.format_error_message(
                "Photo Error",
                "Failed to process the photo. Please try again.",
                code="PHOTO_ERROR"
            )
        )
        return
    
    try:
        cursor.execute("SELECT photos FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        current = result[0] if result else ""
        
        current_count = len(current.split("|")) if current and current.strip() else 0
        if current_count >= 25:
            update.message.reply_text(
                MessageTemplates.format_error_message(
                    "Photo Limit Reached",
                    "Maximum number of photos (25) reached for this job.",
                    code="PHOTO_LIMIT"
                )
            )
            return
        
        new_photos = current.strip() + "|" + photo_path if current and current.strip() else photo_path
        
        cursor.execute("UPDATE grounds_data SET photos = ? WHERE id = ?", (new_photos, job_id))
        conn.commit()
        
        photo_count = len(new_photos.split("|"))
        max_photos = 25
        confirmation_text = MessageTemplates.format_success_message(
            "Photo uploaded",
            f"Photo uploaded for Job {job_id}. ({photo_count}/{max_photos} photos uploaded)"
        )
        
        keyboard = [
            [InlineKeyboardButton("📸 View Photos", callback_data=f"view_photos_{job_id}")],
            [InlineKeyboardButton("📝 Continue Uploading", callback_data=f"upload_photo_{job_id}")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(confirmation_text, reply_markup=markup)
    except sqlite3.Error as e:
        logger.error(f"Database error while saving photo: {str(e)}")
        update.message.reply_text(
            MessageTemplates.format_error_message(
                "Database Error",
                "Failed to save photo. Please try again.",
                code="DB_ERROR"
            )
        )

def handle_text(update: Update, context: CallbackContext):
    if "awaiting_note_for" in context.user_data:
        job_id = context.user_data.pop("awaiting_note_for")
        note = update.message.text
        try:
            cursor.execute("SELECT site_name FROM grounds_data WHERE id = ?", (job_id,))
            result = cursor.fetchone()
            if not result:
                update.message.reply_text(
                    MessageTemplates.format_error_message("Job not found", code="JOB_404")
                )
                return
            
            site_name = result[0]
            cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (note, job_id))
            conn.commit()
            
            keyboard = [
                [InlineKeyboardButton("👀 View Job", callback_data=f"view_job_{job_id}")],
                [InlineKeyboardButton("📝 Edit Again", callback_data=f"edit_note_{job_id}")]
            ]
            markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                MessageTemplates.format_success_message(
                    "Note Updated",
                    f"Note updated for {site_name} (Job {job_id})."
                ),
                reply_markup=markup
            )
        except sqlite3.Error as e:
            logger.error(f"Database error while updating note: {str(e)}")
            update.message.reply_text(
                MessageTemplates.format_error_message(
                    "Database Error",
                    "Failed to update note. Please try again.",
                    code="DB_ERROR"
                )
            )
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
            
            update.message.reply_text(
                MessageTemplates.format_success_message(
                    "Notes Added",
                    f"Notes added to {updated_count} job(s)."
                )
            )
            director_assign_jobs(update, context)
        except sqlite3.Error as e:
            logger.error(f"Database error while adding notes: {str(e)}")
            update.message.reply_text(
                MessageTemplates.format_error_message(
                    "Database Error",
                    "Failed to add notes. Please try again.",
                    code="DB_ERROR"
                )
            )

def handle_toggle_job(update: Update, context: CallbackContext):
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
        text, markup = build_director_assign_jobs_page(current_page, context)
        safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error toggling job selection: {str(e)}")
        update.callback_query.answer(
            "Error toggling job selection. Please try again.",
            show_alert=True
        )

def format_job_section(section_title: str, jobs: list) -> list:
    status_emoji = MessageTemplates.STATUS_EMOJIS.get(jobs[0][5].lower(), '❓')
    sections = [f"\n{status_emoji} {section_title} Jobs:"]
    for job in jobs:
        job_id, site_name, scheduled_date, start_time, finish_time, status, area, notes = job
        duration_str = "N/A"
        if start_time and finish_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                finish_dt = datetime.fromisoformat(finish_time)
                duration = finish_dt - start_dt
                duration_str = str(duration).split('.')[0]
            except Exception:
                duration_str = "N/A"
        sections.append(MessageTemplates.format_job_card(
            site_name=site_name,
            status=status,
            area=area,
            duration=duration_str,
            notes=notes
        ))
    return sections

def create_job_buttons(jobs: list) -> list:
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
        buttons.append([
            InlineKeyboardButton(
                f"{status_emoji} {site_name}{duration}",
                callback_data=f"view_job_{job_id}"
            )
        ])
    return buttons

def build_director_assign_jobs_page(page: int, context: CallbackContext) -> tuple:
    jobs_per_page = 5
    cursor.execute(
        """
        SELECT id, site_name, area, status 
        FROM grounds_data 
        WHERE assigned_to IS NULL 
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (jobs_per_page, page * jobs_per_page)
    )
    jobs = cursor.fetchall()
    
    if not jobs:
        return (
            MessageTemplates.format_success_message(
                "No Jobs Available",
                "There are no unassigned jobs available."
            ),
            InlineKeyboardMarkup([[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]])
        )
    
    selected_jobs = context.user_data.get("selected_jobs", set())
    text_parts = [MessageTemplates.format_job_list_header("Available Jobs", len(jobs))]
    for job_id, site_name, area, status in jobs:
        is_selected = site_name in selected_jobs
        status_emoji = MessageTemplates.STATUS_EMOJIS.get(status.lower(), '❓')
        text_parts.append(
            f"{'✅' if is_selected else '⬜️'} {status_emoji} {site_name} ({area or 'No Area'})"
        )
    
    keyboard = []
    for job_id, site_name, area, status in jobs:
        is_selected = site_name in selected_jobs
        keyboard.append([
            InlineKeyboardButton(
                f"{'✅' if is_selected else '⬜️'} {site_name}",
                callback_data=f"toggle_job_{site_name}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard"))
    if len(jobs) == jobs_per_page:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    keyboard.append(nav_buttons)
    
    if selected_jobs:
        keyboard.append([
            InlineKeyboardButton("📝 Add Notes", callback_data="add_notes"),
            InlineKeyboardButton("✅ Assign Selected", callback_data="assign_selected_jobs")
        ])
    
    return "\n\n".join(text_parts), InlineKeyboardMarkup(keyboard)

def view_job_photos(update: Update, context: CallbackContext):
    query = update.callback_query
    job_id = query.data.split('_')[2]
    
    cursor.execute(
        """
        SELECT photos 
        FROM grounds_data 
        WHERE id = ?
        """,
        (job_id,)
    )
    result = cursor.fetchone()
    
    if not result or not result[0]:
        query.answer("No photos available for this job.")
        return
    
    photo_paths = result[0].split('|')
    media_group = []
    for path in photo_paths:
        try:
            with open(path.strip(), 'rb') as photo:
                media_group.append(InputMediaPhoto(media=photo))
        except Exception as e:
            logger.error(f"Error loading photo {path}: {str(e)}")
            continue
    
    if not media_group:
        query.answer("Error loading photos. Please try again.")
        return
    
    try:
        context.bot.send_media_group(
            chat_id=query.message.chat_id,
            media=media_group,
            caption=f"Photos for job #{job_id}"
        )
        query.answer()
    except Exception as e:
        logger.error(f"Error sending photos: {str(e)}")
        query.answer("Error sending photos. Please try again.")

def director_view_employee_jobs(update: Update, context: CallbackContext, employee_id: int, employee_name: str):
    cursor.execute(
        """
        SELECT id, site_name, scheduled_date, start_time, finish_time, status, area, notes 
        FROM grounds_data 
        WHERE assigned_to = ? AND (scheduled_date IS NULL OR DATE(scheduled_date) = DATE('now','localtime'))
        ORDER BY scheduled_date, id
        """,
        (employee_id,)
    )
    jobs = cursor.fetchall()
    
    if not jobs:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_success_message(
                "No Jobs",
                f"No jobs assigned to {employee_name} today."
            )
        )
        return
    
    sections = [
        MessageTemplates.format_job_list_header(f"{employee_name}'s Jobs", len(jobs))
    ]
    
    active_jobs = [j for j in jobs if j[5] == 'in_progress']
    pending_jobs = [j for j in jobs if j[5] == 'pending']
    completed_jobs = [j for j in jobs if j[5] == 'completed']
    
    if active_jobs:
        sections.extend(format_job_section("Active", active_jobs))
    if pending_jobs:
        sections.extend(format_job_section("Pending", pending_jobs))
    if completed_jobs:
        sections.extend(format_job_section("Completed", completed_jobs))
    
    buttons = create_job_buttons(jobs)
    buttons.append([
        InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")
    ])
    
    safe_edit_text(
        update.callback_query.message,
        "\n\n".join(sections),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def director_view_andys_jobs(update: Update, context: CallbackContext):
    director_view_employee_jobs(update, context, 1672989849, "Andy")

def director_view_alexs_jobs(update: Update, context: CallbackContext):
    director_view_employee_jobs(update, context, 6396234665, "Alex")

#######################################
# DEV FUNCTIONS
#######################################

def dev_dashboard(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    name = employee_users.get(user_id, "Developer")
    header = MessageTemplates.format_dashboard_header(name, "Developer")
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
    message = f"{header}\n\n" + "\n".join(stats)
    markup = ButtonLayouts.create_dev_dashboard(show_stats=True)
    
    if update.callback_query:
        safe_edit_text(update.callback_query.message, message, reply_markup=markup)
    else:
        update.message.reply_text(message, reply_markup=markup)

def dev_director_dashboard(update: Update, context: CallbackContext):
    director_dashboard(update, context)

def dev_employee_dashboard(update: Update, context: CallbackContext):
    emp_employee_dashboard(update, context)

#######################################
# DIRECTOR FUNCTIONS
#######################################

def director_send_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        """
        SELECT site_name, photos, start_time, finish_time, notes, contact, gate_code, map_link, area 
        FROM grounds_data 
        WHERE id = ?
        """,
        (job_id,)
    )
    row = cursor.fetchone()
    if not row:
        safe_edit_text(update.callback_query.message, MessageTemplates.format_error_message("Job not found", code="JOB_404"))
        return

    site_name, photos, start_time, finish_time, notes, contact, gate_code, map_link, area = row
    duration_str = "N/A"
    if start_time and finish_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            finish_dt = datetime.fromisoformat(finish_time)
            duration = finish_dt - start_dt
            duration_str = str(duration).split('.')[0]
        except Exception as e:
            duration_str = "N/A"

    sections = [
        MessageTemplates.format_job_card(
            site_name=site_name,
            status="completed" if finish_time else "in_progress",
            area=area,
            duration=duration_str,
            notes=notes
        )
    ]

    if contact or gate_code:
        sections.append(
            MessageTemplates.format_site_info(
                site_name=site_name,
                contact=contact,
                gate_code=gate_code,
                address=None,
                special_instructions=None
            )
        )

    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]
    ]
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
                    logger.error(f"Error preparing photo for job {job_id}: {str(e)}")
            else:
                logger.warning(f"Photo file not found: {abs_path}")

        if media_group:
            max_items = 10
            chunks = [media_group[i:i + max_items] for i in range(0, len(media_group), max_items)]
            for index, chunk in enumerate(chunks):
                if index == 0:
                    if len(chunk) == 1:
                        update.callback_query.message.reply_photo(
                            photo=chunk[0].media,
                            caption="\n\n".join(sections),
                            reply_markup=markup
                        )
                    else:
                        update.callback_query.message.reply_media_group(media=chunk)
                        update.callback_query.message.reply_text(
                            "\n\n".join(sections),
                            reply_markup=markup
                        )
                else:
                    update.callback_query.message.reply_media_group(media=chunk)
        else:
            safe_edit_text(update.callback_query.message, "\n\n".join(sections), reply_markup=markup)
    else:
        safe_edit_text(update.callback_query.message, "\n\n".join(sections), reply_markup=markup)

def director_select_day_for_assignment(update: Update, context: CallbackContext):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    keyboard = []
    for day in days:
        keyboard.append([InlineKeyboardButton(day, callback_data=f"assign_day_{day}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    
    current_hour = datetime.now().hour
    greeting = "Good Morning" if current_hour < 12 else "Good Afternoon"
    header = f"{greeting}! Please select a day of the week for assignment:"
    safe_edit_text(update.callback_query.message, header, reply_markup=markup)

def director_assign_day_selected(update: Update, context: CallbackContext):
    selected_day = update.callback_query.data.split("_")[-1]
    context.user_data["selected_day"] = selected_day
    
    keyboard = []
    for emp_id, emp_name in employee_users.items():
        keyboard.append([InlineKeyboardButton(f"Assign to {emp_name}", callback_data=f"assign_to_{emp_id}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    
    message = MessageTemplates.format_success_message(
        "Day Selected",
        f"You selected {selected_day}. Please choose an employee to assign the selected jobs."
    )
    safe_edit_text(update.callback_query.message, message, reply_markup=markup)

def director_dashboard(update: Update, context: CallbackContext):
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
    message = f"{header}\n\n" + "\n".join(stats)
    markup = ButtonLayouts.create_director_dashboard(show_stats=True)
    
    if update.callback_query:
        safe_edit_text(update.callback_query.message, message, reply_markup=markup)
    else:
        update.message.reply_text(message, reply_markup=markup)

def director_add_notes(update: Update, context: CallbackContext):
    if "selected_jobs" not in context.user_data or not context.user_data["selected_jobs"]:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "No Jobs Selected",
                "Please select jobs before adding notes.",
                code="NO_JOBS_SELECTED"
            )
        )
        return
    
    context.user_data["awaiting_notes"] = True
    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data="director_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    safe_edit_text(
        update.callback_query.message,
        MessageTemplates.format_input_prompt("Please send the notes to add to the selected jobs:")
    )

def director_edit_note(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT site_name FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message("Job not found", code="JOB_404")
            )
            return
        site_name = result[0]
        context.user_data["awaiting_note_for"] = job_id
        keyboard = [
            [InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data=f"cancel_note_{job_id}")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_input_prompt(f"Please send the note for {site_name} (Job {job_id}):")
        )
    except sqlite3.Error as e:
        logger.error(f"Database error while preparing note edit: {str(e)}")
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "Database Error",
                "Failed to prepare note editing. Please try again.",
                code="DB_ERROR"
            )
        )

def director_cancel_note(update: Update, context: CallbackContext):
    director_send_job(update, context)

def director_assign_jobs(update: Update, context: CallbackContext):
    if "selected_jobs" not in context.user_data or not context.user_data["selected_jobs"]:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "No Jobs Selected",
                "Please select jobs before assigning.",
                code="NO_JOBS_SELECTED"
            )
        )
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
    
    message = MessageTemplates.format_success_message(
        "Select Employee",
        "Please choose an employee to assign the selected jobs."
    )
    safe_edit_text(update.callback_query.message, message, reply_markup=markup)

def assign_jobs_to_employee(update: Update, context: CallbackContext):
    employee_id = int(update.callback_query.data.split("_")[-1])
    selected_jobs = context.user_data.get("selected_jobs", set())
    selected_day = context.user_data.get("selected_day")
    
    if not selected_jobs:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "No Jobs Selected",
                "Please select jobs before assigning.",
                code="NO_JOBS_SELECTED"
            )
        )
        return
    
    if not selected_day:
        director_select_day_for_assignment(update, context)
        return
    
    try:
        for site_name in selected_jobs:
            cursor.execute(
                "UPDATE grounds_data SET assigned_to = ?, scheduled_date = ? WHERE site_name = ?",
                (employee_id, selected_day, site_name)
            )
        conn.commit()
        
        message = MessageTemplates.format_success_message(
            "Jobs Assigned",
            f"Selected jobs have been assigned to {employee_users.get(employee_id, 'Employee')} for {selected_day}."
        )
        safe_edit_text(update.callback_query.message, message)
        
        if "selected_jobs" in context.user_data:
            del context.user_data["selected_jobs"]
        if "selected_day" in context.user_data:
            del context.user_data["selected_day"]
        
        director_dashboard(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while assigning jobs: {str(e)}")
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "Database Error",
                "Failed to assign jobs. Please try again.",
                code="DB_ERROR"
            )
        )

def director_calendar_view(update: Update, context: CallbackContext):
    text = MessageTemplates.format_success_message(
        "Calendar View",
        "Calendar View: [Feature coming soon - This is a stub]"
    )
    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    safe_edit_text(update.callback_query.message, text, reply_markup=markup)

#######################################
# EMPLOYEE FUNCTIONS
#######################################

def emp_employee_dashboard(update: Update, context: CallbackContext):
    if "awaiting_photo_for" in context.user_data:
        del context.user_data["awaiting_photo_for"]
    
    back_callback = "dev_dashboard" if update.effective_user.id in dev_users else "start"
    keyboard = [
        [InlineKeyboardButton("📋 View My Jobs", callback_data="emp_view_jobs")],
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=back_callback)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    text = MessageTemplates.format_dashboard_header(
        employee_users.get(update.effective_user.id, "Employee"),
        "Employee"
    )
    
    if update.callback_query:
        safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif update.message:
        update.message.reply_text(text, reply_markup=markup)

def emp_view_jobs(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute(
        """
        SELECT id, site_name, area, status, notes, start_time, finish_time 
        FROM grounds_data 
        WHERE assigned_to = ? AND (start_time IS NULL OR DATE(start_time) = DATE('now', 'localtime'))
        """,
        (user_id,)
    )
    jobs = cursor.fetchall()
    
    if not jobs:
        message = MessageTemplates.format_success_message(
            "No Jobs",
            "You have no assigned jobs today."
        )
        if update.callback_query:
            safe_edit_text(update.callback_query.message, message)
        elif update.message:
            update.message.reply_text(message)
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
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix}{site_name} ({area or 'No Area'}) [{status.capitalize()}]{duration}",
                callback_data=f"job_menu_{job_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="emp_employee_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    
    message = MessageTemplates.format_job_list_header("Your Jobs (Today)", len(jobs))
    if update.callback_query:
        safe_edit_text(update.callback_query.message, message, reply_markup=markup)
    elif update.message:
        update.message.reply_text(message, reply_markup=markup)

def emp_job_menu(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        """
        SELECT site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link, photos 
        FROM grounds_data 
        WHERE id = ?
        """,
        (job_id,)
    )
    job_data = cursor.fetchone()
    
    if not job_data:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message("Job not found", code="JOB_404")
        )
        return
    
    site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link, photos = job_data
    
    sections = [
        MessageTemplates.format_job_card(
            site_name=site_name,
            status=status,
            area=area,
            duration=str(datetime.fromisoformat(finish_time) - datetime.fromisoformat(start_time)).split('.')[0] if start_time and finish_time else "N/A",
            notes=notes
        )
    ]
    
    if contact or gate_code:
        sections.append(MessageTemplates.format_site_info(
            site_name=site_name,
            contact=contact,
            gate_code=gate_code,
            address=None,
            special_instructions=None
        ))
    
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
    
    safe_edit_text(
        update.callback_query.message,
        "\n\n".join(sections),
        reply_markup=markup
    )

def emp_start_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT status FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message("Job not found", code="JOB_404")
            )
            return
        
        current_status = result[0]
        if current_status == 'in_progress':
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message(
                    "Already Started",
                    "This job is already in progress.",
                    code="JOB_IN_PROGRESS"
                )
            )
            return
        
        cursor.execute(
            "UPDATE grounds_data SET status = 'in_progress', start_time = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id)
        )
        conn.commit()
        
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_success_message(
                "Job Started",
                f"Job {job_id} has been started."
            )
        )
        emp_view_jobs(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while starting job: {str(e)}")
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "Database Error",
                "Failed to start job. Please try again.",
                code="DB_ERROR"
            )
        )

def emp_finish_job(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    try:
        cursor.execute("SELECT status FROM grounds_data WHERE id = ?", (job_id,))
        result = cursor.fetchone()
        if not result:
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message("Job not found", code="JOB_404")
            )
            return
        
        current_status = result[0]
        if current_status == 'completed':
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message(
                    "Already Completed",
                    "This job is already completed.",
                    code="JOB_COMPLETED"
                )
            )
            return
        
        if current_status != 'in_progress':
            safe_edit_text(
                update.callback_query.message,
                MessageTemplates.format_error_message(
                    "Not Started",
                    "This job has not been started yet.",
                    code="JOB_NOT_STARTED"
                )
            )
            return
        
        cursor.execute(
            "UPDATE grounds_data SET status = 'completed', finish_time = ? WHERE id = ?",
            (datetime.now().isoformat(), job_id)
        )
        conn.commit()
        
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_success_message(
                "Job Completed",
                f"Job {job_id} has been completed."
            )
        )
        emp_view_jobs(update, context)
    except sqlite3.Error as e:
        logger.error(f"Database error while finishing job: {str(e)}")
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "Database Error",
                "Failed to complete job. Please try again.",
                code="DB_ERROR"
            )
        )

def emp_upload_photo(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["awaiting_photo_for"] = job_id
    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data=f"job_menu_{job_id}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    safe_edit_text(
        update.callback_query.message,
        MessageTemplates.format_input_prompt("Please send the photo for this job:")
    )

def emp_site_info(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        "SELECT site_name, contact, gate_code, address FROM grounds_data WHERE id = ?",
        (job_id,)
    )
    job_data = cursor.fetchone()
    
    if not job_data:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message("Job not found", code="JOB_404")
        )
        return
    
    site_name, contact, gate_code, address = job_data
    info_text = MessageTemplates.format_site_info(
        site_name=site_name,
        contact=contact,
        gate_code=gate_code,
        address=address,
        special_instructions=None
    )
    
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=f"job_menu_{job_id}")]]
    markup = InlineKeyboardMarkup(keyboard)
    safe_edit_text(update.callback_query.message, info_text, reply_markup=markup)

def emp_map_link(update: Update, context: CallbackContext):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, map_link FROM grounds_data WHERE id = ?", (job_id,))
    job_data = cursor.fetchone()
    
    if not job_data:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message("Job not found", code="JOB_404")
        )
        return
    
    site_name, map_link = job_data
    if not map_link:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "No Map Link",
                "No map link available for this job.",
                code="NO_MAP_LINK"
            )
        )
        return
    
    keyboard = [[InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data=f"job_menu_{job_id}")]]
    markup = InlineKeyboardMarkup(keyboard)
    safe_edit_text(
        update.callback_query.message,
        f"🗺 Map Link for {site_name}:\n{map_link}",
        reply_markup=markup
    )

#######################################
# CALLBACK QUERY HANDLER
#######################################

def callback_handler(update: Update, context: CallbackContext):
    data = update.callback_query.data
    update.callback_query.answer()
    
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
        handlers[data](update, context)
        return
    
    if data.startswith("select_day_"):
        director_select_day_for_assignment(update, context)
    elif data.startswith("assign_day_"):
        director_assign_day_selected(update, context)
    elif data.startswith("dir_assign_jobs_"):
        director_assign_jobs(update, context)
    elif data.startswith("toggle_job_"):
        handle_toggle_job(update, context)
    elif data.startswith("assign_to_"):
        assign_jobs_to_employee(update, context)
    elif data.startswith("job_menu_"):
        emp_job_menu(update, context)
    elif data.startswith("upload_photo_"):
        emp_upload_photo(update, context)
    elif data.startswith("site_info_"):
        emp_site_info(update, context)
    elif data.startswith("start_job_"):
        emp_start_job(update, context)
    elif data.startswith("finish_job_"):
        emp_finish_job(update, context)
    elif data.startswith("map_link_"):
        emp_map_link(update, context)
    elif data.startswith("send_job_"):
        director_send_job(update, context)
    elif data.startswith("edit_note_"):
        director_edit_note(update, context)
    elif data.startswith("cancel_note_"):
        director_cancel_note(update, context)
    elif data.startswith("view_job_"):
        director_send_job(update, context)
    elif data.startswith("view_photos_"):
        view_job_photos(update, context)
    elif data.startswith("page_"):
        page = int(data.split("_")[-1])
        context.user_data["current_page"] = page
        text, markup = build_director_assign_jobs_page(page, context)
        safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif data == "noop":
        pass
    else:
        safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message(
                "Unknown Action",
                "This action is not supported.",
                code="UNKNOWN_ACTION"
            )
        )

#######################################
# DAILY RESET FUNCTION
#######################################

def reset_completed_jobs():
    logger.info("Resetting completed jobs for a new day.")
    cursor.execute("UPDATE grounds_data SET status = 'pending', assigned_to = NULL, finish_time = NULL WHERE status = 'completed' AND (scheduled_date IS NULL OR scheduled_date = date('now','localtime'))")
    conn.commit()

#######################################
# START COMMAND
#######################################

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "Dev":
        dev_dashboard(update, context)
    elif role == "Director":
        director_dashboard(update, context)
    elif role == "Employee":
        emp_employee_dashboard(update, context)
    else:
        text = MessageTemplates.format_error_message(
            "Access Denied",
            "You do not have a registered role.",
            code="ROLE_404"
        )
        if update.callback_query:
            update.callback_query.message.reply_text(text)
        else:
            update.message.reply_text(text)

#######################################
# HELP COMMAND
#######################################

def help_command(update: Update, context: CallbackContext):
    text = (
        "🤖 *Bot Help*\n\n"
        "*/start* - Launch the bot and navigate to your dashboard.\n"
        "*/help* - Show this help message.\n\n"
        "Use the inline buttons to navigate dashboards and manage jobs.\n"
        "- *Director*: View/assign jobs, edit individual job notes, view job details with photos, and use the Calendar for scheduling by day.\n"
        "- *Employee*: View your assigned jobs (only today's), start/finish jobs, and upload photos.\n"
        "- *Dev*: Access debug dashboards with Back buttons to return to the Dev Dashboard.\n\n"
        "If you have any questions, ask your system admin."
    )
    if update.callback_query:
        update.callback_query.message.reply_text(text, parse_mode="Markdown")
    else:
        update.message.reply_text(text, parse_mode="Markdown")

#######################################
# MAIN FUNCTION & SCHEDULER SETUP
#######################################

def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(MessageHandler(Filters.photo & ~Filters.command, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dispatcher.add_handler(CallbackQueryHandler(callback_handler))
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('UTC'))
    scheduler.add_job(reset_completed_jobs, 'cron', hour=0, minute=0)
    scheduler.start()
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
