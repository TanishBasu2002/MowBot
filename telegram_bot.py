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

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.error import BadRequest

from src.bot.utils.message_templates import MessageTemplates
from src.bot.utils.button_layouts import ButtonLayouts
from src.bot.database.models import get_db, Ground
from src.bot.services.ground_service import GroundService
from src.bot.utils.decorators import error_handler, director_only, employee_only

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
# HELPER: Safe Edit Text Function
#######################################

async def safe_edit_text(message, text, reply_markup=None):
    """Attempt to edit a message; if it fails, send a new message."""
    try:
        if message.text and message.text.strip():
            return await message.edit_text(text, reply_markup=reply_markup)
        else:
            return await message.reply_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        logger.error(f"safe_edit_text error: {str(e)}")
        return await message.reply_text(text, reply_markup=reply_markup)

#######################################
# DAILY RESET FUNCTION
#######################################

async def reset_completed_jobs():
    logger.info("Resetting completed jobs for a new day.")
    cursor.execute("UPDATE grounds_data SET status = 'pending', assigned_to = NULL, finish_time = NULL WHERE status = 'completed' AND (scheduled_date IS NULL OR scheduled_date = date('now','localtime'))")
    conn.commit()

#######################################
# PHOTO UPLOAD ENHANCEMENT
#######################################

async def director_send_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, photos, start_time, finish_time, notes FROM grounds_data WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        await safe_edit_text(update.callback_query.message, MessageTemplates.format_error_message("Job not found", code="JOB_404"))
        return
    
    site_name, photos, start_time, finish_time, notes = row
    duration_str = "N/A"
    if start_time and finish_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            finish_dt = datetime.fromisoformat(finish_time)
            duration = finish_dt - start_dt
            duration_str = str(duration).split('.')[0]
        except Exception as e:
            duration_str = "N/A"
    
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
    
    detail_text = MessageTemplates.format_job_card(
        site_name=site_name,
        status="completed" if finish_time else "in_progress",
        duration=duration_str,
        notes=notes
    )
    
    keyboard = ButtonLayouts.create_job_menu(
        job_id=job_id,
        status="completed" if finish_time else "in_progress",
        has_photos=bool(photos),
        has_notes=bool(notes)
    )
    markup = InlineKeyboardMarkup(keyboard)
    
    if media_group:
        max_items = 10
        chunks = [media_group[i:i + max_items] for i in range(0, len(media_group), max_items)]
        for index, chunk in enumerate(chunks):
            if index == 0:
                if len(chunk) == 1:
                    await update.callback_query.message.reply_photo(photo=chunk[0].media, caption=detail_text, reply_markup=markup)
                else:
                    await update.callback_query.message.reply_media_group(media=chunk)
                    await update.callback_query.message.reply_text(detail_text, reply_markup=markup)
            else:
                await update.callback_query.message.reply_media_group(media=chunk)
    else:
        await safe_edit_text(update.callback_query.message, detail_text, reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_photo_for" not in context.user_data:
        return
    
    job_id = context.user_data["awaiting_photo_for"]
    photo_file = await update.message.photo[-1].get_file()
    photo_dir = "photos"
    os.makedirs(photo_dir, exist_ok=True)
    photo_filename = f"job_{job_id}_{photo_file.file_id}.jpg"
    photo_path = os.path.join(photo_dir, photo_filename)
    await photo_file.download_to_drive(custom_path=photo_path)
    
    cursor.execute("SELECT photos FROM grounds_data WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    current = result[0] if result else ""
    if current and current.strip():
        new_photos = current.strip() + "|" + photo_path
    else:
        new_photos = photo_path
    
    cursor.execute("UPDATE grounds_data SET photos = ? WHERE id = ?", (new_photos, job_id))
    conn.commit()
    
    photo_count = len(new_photos.split("|"))
    max_photos = 25
    confirmation_text = MessageTemplates.format_success_message(
        "Photo uploaded",
        f"Photo uploaded for Job {job_id}. ({photo_count}/{max_photos} photos uploaded)"
    )
    await update.message.reply_text(confirmation_text)

#######################################
# JOB ASSIGNMENT & DAY SELECTION
#######################################

async def director_select_day_for_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    keyboard = []
    for day in days:
        keyboard.append([InlineKeyboardButton(day, callback_data=f"assign_day_{day}")])
    keyboard.append([InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    
    current_hour = datetime.now().hour
    greeting = "Good Morning" if current_hour < 12 else "Good Afternoon"
    header = f"{greeting}! Please select a day of the week for assignment:"
    await safe_edit_text(update.callback_query.message, header, reply_markup=markup)

async def director_assign_day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await safe_edit_text(update.callback_query.message, message, reply_markup=markup)

#######################################
# DIRECTOR DASHBOARD
#######################################

async def director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = employee_users.get(user_id, "Director")
    
    # Create dashboard header with stats
    header = MessageTemplates.format_dashboard_header(name, "Director")
    
    # Get quick stats
    total_jobs = len(cursor.execute("SELECT id FROM grounds_data").fetchall())
    active_jobs = len(cursor.execute("SELECT id FROM grounds_data WHERE status = 'in_progress'").fetchall())
    completed_jobs = len(cursor.execute("SELECT id FROM grounds_data WHERE status = 'completed'").fetchall())
    
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
    
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, message, reply_markup=markup)
    else:
        await update.message.reply_text(message, reply_markup=markup)

#######################################
# DIRECTOR: View Employee Jobs
#######################################

async def director_view_employee_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE, employee_id: int, employee_name: str):
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
        await safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_success_message(
                "No Jobs",
                f"No jobs assigned to {employee_name} today."
            )
        )
        return
    
    # Create message sections
    sections = [
        MessageTemplates.format_job_list_header(f"{employee_name}'s Jobs", len(jobs))
    ]
    
    # Group jobs by status
    active_jobs = [j for j in jobs if j[5] == 'in_progress']
    pending_jobs = [j for j in jobs if j[5] == 'pending']
    completed_jobs = [j for j in jobs if j[5] == 'completed']
    
    # Add job sections with enhanced formatting
    if active_jobs:
        sections.extend(format_job_section("Active", active_jobs))
    if pending_jobs:
        sections.extend(format_job_section("Pending", pending_jobs))
    if completed_jobs:
        sections.extend(format_job_section("Completed", completed_jobs))
    
    # Create interactive buttons for each job
    buttons = create_job_buttons(jobs)
    buttons.append([
        InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")
    ])
    
    await safe_edit_text(
        update.callback_query.message,
        "\n\n".join(sections),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def format_job_section(section_title: str, jobs: list) -> list:
    """Format a section of jobs with consistent styling."""
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
    """Create interactive buttons for jobs with status indicators."""
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

async def director_view_andys_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await director_view_employee_jobs(update, context, 1672989849, "Andy")

async def director_view_alexs_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await director_view_employee_jobs(update, context, 6396234665, "Alex")

#######################################
# EMPLOYEE DASHBOARD & FEATURES
#######################################

async def emp_employee_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup)

async def emp_view_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await safe_edit_text(update.callback_query.message, message)
        elif update.message:
            await update.message.reply_text(message)
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
        await safe_edit_text(update.callback_query.message, message, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(message, reply_markup=markup)

async def emp_job_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        """
        SELECT site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link 
        FROM grounds_data 
        WHERE id = ?
        """,
        (job_id,)
    )
    job_data = cursor.fetchone()
    
    if not job_data:
        await safe_edit_text(
            update.callback_query.message,
            MessageTemplates.format_error_message("Job not found", code="JOB_404")
        )
        return
    
    site_name, status, notes, start_time, finish_time, area, contact, gate_code, map_link = job_data
    
    # Format job information
    sections = [
        MessageTemplates.format_job_card(
            site_name=site_name,
            status=status,
            area=area,
            duration=str(datetime.fromisoformat(finish_time) - datetime.fromisoformat(start_time)).split('.')[0] if start_time and finish_time else "N/A",
            notes=notes
        )
    ]
    
    # Add site information if available
    if contact or gate_code:
        sections.append(MessageTemplates.format_site_info(
            site_name=site_name,
            contact=contact,
            gate_code=gate_code,
            address=None,
            special_instructions=None
        ))
    
    # Create context-aware button menu
    markup = ButtonLayouts.create_job_menu(
        job_id=job_id,
        status=status,
        has_photos=False,  # You might want to check this from the database
        has_notes=bool(notes)
    )
    
    await safe_edit_text(
        update.callback_query.message,
        "\n\n".join(sections),
        reply_markup=markup
    )

async def emp_start_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        "UPDATE grounds_data SET status = 'in_progress', start_time = ? WHERE id = ?",
        (datetime.now().isoformat(), job_id)
    )
    conn.commit()
    
    await safe_edit_text(
        update.callback_query.message,
        MessageTemplates.format_success_message(
            "Job Started",
            f"Job {job_id} has been started."
        )
    )
    await emp_view_jobs(update, context)

async def emp_finish_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute(
        "UPDATE grounds_data SET status = 'completed', finish_time = ? WHERE id = ?",
        (datetime.now().isoformat(), job_id)
    )
    conn.commit()
    
    await safe_edit_text(
        update.callback_query.message,
        MessageTemplates.format_success_message(
            "Job Completed",
            f"Job {job_id} has been completed."
        )
    )
    await emp_view_jobs(update, context)

#######################################
# NOTE EDITING FUNCTIONALITY
#######################################

async def director_edit_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["awaiting_note_for"] = job_id
    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.CANCEL_PREFIX} Cancel", callback_data=f"cancel_note_{job_id}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(
        update.callback_query.message,
        MessageTemplates.format_input_prompt("Please send the note for Job {job_id}:")
    )

async def director_cancel_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await director_send_job(update, context)

#######################################
# TEXT HANDLER
#######################################

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_note_for" in context.user_data:
        job_id = context.user_data.pop("awaiting_note_for")
        note = update.message.text
        cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (note, job_id))
        conn.commit()
        await update.message.reply_text(
            MessageTemplates.format_success_message(
                "Note Updated",
                f"Note updated for Job {job_id}."
            )
        )
        return
    
    if "awaiting_notes" in context.user_data and context.user_data["awaiting_notes"]:
        notes = update.message.text
        selected_jobs = context.user_data.get("selected_jobs", set())
        for site_name in selected_jobs:
            cursor.execute("SELECT id FROM grounds_data WHERE site_name = ?", (site_name,))
            job = cursor.fetchone()
            if job:
                cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (notes, job[0]))
        conn.commit()
        await update.message.reply_text(
            MessageTemplates.format_success_message(
                "Notes Added",
                f"Notes added to {len(selected_jobs)} job(s)."
            )
        )
        await director_assign_jobs(update, context)

#######################################
# CALLBACK QUERY HANDLER
#######################################

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "dir_assign_jobs": director_assign_jobs
    }
    
    # Handle direct matches
    if data in handlers:
        await handlers[data](update, context)
        return
    
    # Handle prefixed matches
    if data.startswith("select_day_"):
        await director_select_day_for_assignment(update, context)
    elif data == "select_day_for_assignment":
        await director_select_day_for_assignment(update, context)
    elif data.startswith("assign_day_"):
        await director_assign_day_selected(update, context)
    elif data.startswith("dir_assign_jobs_"):
        await director_assign_jobs(update, context)
    elif data == "assign_selected_jobs":
        await director_select_day_for_assignment(update, context)
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
    elif data.startswith("page_"):
        page = int(data.split("_")[-1])
        text, markup = build_director_assign_jobs_page(page, context)
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif data == "noop":
        pass

async def handle_toggle_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    site_name = update.callback_query.data.split("_", 2)[-1]
    if "selected_jobs" not in context.user_data:
        context.user_data["selected_jobs"] = set()
    selected_jobs = context.user_data["selected_jobs"]
    
    if site_name in selected_jobs:
        selected_jobs.remove(site_name)
    else:
        selected_jobs.add(site_name)
    
    logger.info(f"Toggled {site_name} - selected_jobs now: {selected_jobs}")
    page = context.user_data.get("current_page", 0)
    text, markup = build_director_assign_jobs_page(page, context)
    await safe_edit_text(update.callback_query.message, text, reply_markup=markup)

#######################################
# DEV DASHBOARD FUNCTIONS
#######################################

async def dev_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = MessageTemplates.format_dashboard_header("Developer", "Dev")
    keyboard = [
        [InlineKeyboardButton("Director Dashboard", callback_data="dev_director_dashboard")],
        [InlineKeyboardButton("Employee Dashboard", callback_data="dev_employee_dashboard")],
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back to Start", callback_data="start")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = MessageTemplates.format_dashboard_header("Developer Director", "Dev")
    keyboard = [
        [InlineKeyboardButton("Director Dashboard", callback_data="director_dashboard")],
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back to Dev Dashboard", callback_data="dev_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_employee_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = MessageTemplates.format_dashboard_header("Developer Employee", "Dev")
    keyboard = [
        [InlineKeyboardButton("Employee Dashboard", callback_data="emp_employee_dashboard")],
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back to Dev Dashboard", callback_data="dev_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

#######################################
# DIRECTOR CALENDAR VIEW
#######################################

async def director_calendar_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = MessageTemplates.format_success_message(
        "Calendar View",
        "Calendar View: [Feature coming soon - This is a stub]"
    )
    keyboard = [
        [InlineKeyboardButton(f"{ButtonLayouts.BACK_PREFIX} Back", callback_data="director_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update.callback_query.message, text, reply_markup=markup)

#######################################
# START COMMAND
#######################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "Dev":
        await dev_dashboard(update, context)
    elif role == "Director":
        await director_dashboard(update, context)
    elif role == "Employee":
        await emp_employee_dashboard(update, context)
    else:
        text = MessageTemplates.format_error_message(
            "Access Denied",
            "You do not have a registered role.",
            code="ROLE_404"
        )
        if update.callback_query:
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)

#######################################
# HELP COMMAND
#######################################

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.callback_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

#######################################
# MAIN FUNCTION & SCHEDULER SETUP
#######################################

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Setup scheduler
    scheduler = AsyncIOScheduler(event_loop=loop)
    scheduler.add_job(reset_completed_jobs, 'cron', hour=0, minute=0)
    scheduler.start()
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
