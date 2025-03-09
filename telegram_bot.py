######################################################
# TELEGRAM_BOT.PY (ULTIMATE VERSION V7 - UPDATED DASHBOARDS, CALENDAR & NOTE EDITING)
#
# Features:
# - Director: Updated dashboard shows current date/time with buttons for:
#     • Assign Jobs
#     • View Andy's Jobs (Today)
#     • View Alex's Jobs (Today)
#     • Calendar (Weekly view)
#   In the job detail view, the Director can see times, photos,
#   and add/edit an individual note.
# - Employee: Dashboard displays only today’s jobs (old jobs reset daily).
# - Dev: Dev role includes Back buttons to return to the Dev Dashboard.
# - Daily Reset: At midnight, completed jobs are reset.
# - User IDs: 1672989849 as Dev/Director/Andy, 6396234665 as Alex.
# - Future AI Integration: (Comments outline collecting scheduling data for future AI analysis)
# - /help command is provided.
######################################################

import os
import logging
import sqlite3
from datetime import datetime
import asyncio

from datetime import datetime, timedelta
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

#####################
# ENV & TOKEN SETUP
#####################

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Set your token in .env

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#####################
# ROLES & USERS
#####################

dev_users = {1672989849}                # Dev (and Andy/Director)
director_users = {1672989849, 7996550019, 8018680694}  # Updated directors
employee_users = {1672989849: "Andy", 6396234665: "Alex"}  # Alex's updated ID

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
        notes TEXT
    );
    """
)
cursor.executescript(""" 
    CREATE INDEX IF NOT EXISTS idx_grounds_assigned_to ON grounds_data(assigned_to);
    CREATE INDEX IF NOT EXISTS idx_grounds_status ON grounds_data(status);
    CREATE INDEX IF NOT EXISTS idx_grounds_site_name ON grounds_data(site_name);
""")
cursor.execute("SELECT COUNT(*) FROM grounds_data")
if cursor.fetchone()[0] == 0:
    sites_list = [
        ('Mercedes-Benz', 'QU-1336(4)', 'Lysander Road, Cribbs Causeway', 'Lysander Rd', 'Ongoing', 'Cribbs', 'Fortnightly 1 March to 31 October', 'Fortnightly', 'Unknown', 'Unknown', 'https://maps.google.com/?q=Lysander+Road+Cribbs+Causeway', None, 'pending', None, None, None, None),
        ('HML - The Park', 'QU-1122(2)', 'The Park, Hartcliffe', 'C307679', '', 'Hartcliffe', 'Fortnightly 1 March to 31 October', 'Monthly', 'Unknown', 'Unknown', 'https://maps.google.com/?q=The+Park+Hartcliffe', None, 'pending', None, None, None, None),
        # ... (Other sites omitted for brevity) ...
        ('Lowther Forestry', 'QU-1902', 'Bolingbroke Way', 'WM-3377', 'Mar-Oct', 'BS34', 'Fortnightly 1 March to 31 October', 'NONE', 'Unknown', 'Unknown', 'https://maps.google.com/?q=Bolingbroke+Way+BS34', None, 'pending', None, None, None, None)
    ]
    for site_name, quote, address, order_no, order_period, area, summer, winter, contact, gate_code, map_link, assigned_to, status, photos, start_time, finish_time, notes in sites_list:
        cursor.execute(
            "INSERT INTO grounds_data (site_name, quote, address, order_no, order_period, area, summer_schedule, winter_schedule, contact, gate_code, map_link, assigned_to, status, photos, start_time, finish_time, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (site_name, quote, address, order_no, order_period, area, summer, winter, contact, gate_code, map_link, assigned_to, status, photos, start_time, finish_time, notes)
        )
    conn.commit()

#######################################
# HELPER: Safe Edit Text Function
#######################################

async def safe_edit_text(message, text, reply_markup=None):
    """Tries to edit a message; if it fails (e.g., message is empty), sends a new message."""
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
    cursor.execute("UPDATE grounds_data SET status = 'pending', assigned_to = NULL, finish_time = NULL WHERE status = 'completed'")
    conn.commit()

#######################################
# CALENDAR INTEGRATION (WEEKLY VIEW)
#######################################

async def director_calendar_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a simple inline calendar for the current week."""
    today = datetime.now()
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Build inline keyboard with days of the week
    keyboard = []
    for i, day in enumerate(days):
        # For simplicity, assume the week starts on Monday of the current week.
        day_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        # Calculate the date for this day in the week:
        monday = today - timedelta(days=today.weekday())
        selected_date = monday + timedelta(days=i)
        button_text = f"{day} ({selected_date.strftime('%m/%d')})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_day_{selected_date.strftime('%Y-%m-%d')}")])
    # Add a back button
    keyboard.append([InlineKeyboardButton("Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    header = f"Weekly Calendar View\nSelect a day to view or assign jobs:"
    await safe_edit_text(update.callback_query.message, header, reply_markup=markup)

async def director_select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles selection of a day from the calendar view."""
    day = update.callback_query.data.split("_")[-1]
    # For now, simply inform the user of the selected day.
    text = f"Selected day: {day}\n[Calendar scheduling functionality not fully implemented yet.]"
    # Later, this function can query the DB for jobs scheduled on that day.
    await safe_edit_text(update.callback_query.message, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="director_dashboard")]]))

#######################################
# HELPER: Build Director Assign Jobs Page (unchanged)
#######################################

def build_director_assign_jobs_page(page: int, context: ContextTypes.DEFAULT_TYPE):
    sites_per_page = 20
    cursor.execute("SELECT site_name, area FROM grounds_data ORDER BY area")
    all_sites = cursor.fetchall()
    cursor.execute("SELECT site_name, assigned_to FROM grounds_data")
    job_status = {row[0]: row[1] for row in cursor.fetchall()}
    if not all_sites:
        return "📝 No sites available.", InlineKeyboardMarkup([])
    start_idx = page * sites_per_page
    end_idx = start_idx + sites_per_page
    page_sites = all_sites[start_idx:end_idx]
    site_keyboard = []
    if "selected_jobs" not in context.user_data:
        context.user_data["selected_jobs"] = set()
    selected_jobs = context.user_data["selected_jobs"]
    logger.info(f"Building assign jobs page {page} - selected_jobs: {selected_jobs}")
    areas = {}
    for site_name, area in page_sites:
        area = area or "No Area"
        areas.setdefault(area, []).append(site_name)
    for area, sites in areas.items():
        site_keyboard.append([InlineKeyboardButton(f"📍 {area}", callback_data="noop")])
        for i in range(0, len(sites), 2):
            row = []
            for j in range(2):
                if i + j < len(sites):
                    site_name = sites[i + j]
                    assigned_to = job_status.get(site_name)
                    status_symbol = "✅" if assigned_to else "⬜"
                    prefix = "✅ " if site_name in selected_jobs else f"{status_symbol} "
                    row.append(InlineKeyboardButton(f"{prefix}{site_name}", callback_data=f"toggle_job_{site_name}"))
            site_keyboard.append(row)
    action_keyboard = [
        [InlineKeyboardButton("Add Notes (Batch)", callback_data="add_notes")],
        [InlineKeyboardButton("Back", callback_data="director_dashboard")]
    ]
    if selected_jobs:
        action_keyboard.insert(0, [InlineKeyboardButton("Continue", callback_data="assign_selected_jobs")])
        logger.info(f"Continue button added - selected_jobs: {selected_jobs}")
    pagination_keyboard = []
    if page > 0:
        pagination_keyboard.append(InlineKeyboardButton("Previous", callback_data=f"dir_assign_jobs_{page-1}"))
    if end_idx < len(all_sites):
        pagination_keyboard.append(InlineKeyboardButton("Next", callback_data=f"dir_assign_jobs_{page+1}"))
    if pagination_keyboard:
        action_keyboard.append(pagination_keyboard)
    keyboard = site_keyboard + action_keyboard
    text = f"📝 Select jobs to assign (Page {page + 1}, Selected: {len(selected_jobs)}):"
    return text, InlineKeyboardMarkup(keyboard)

#######################################
# DEV DASHBOARD & DEV FUNCTIONS
#######################################

async def dev_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👷 Employee Dashboard", callback_data="dev_employee_dashboard")],
        [InlineKeyboardButton("📊 Director Dashboard", callback_data="dev_director_dashboard")],
        [InlineKeyboardButton("Back", callback_data="start")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = "🛠️ Dev Dashboard:"
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_employee_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    back_callback = "dev_dashboard" if update.effective_user.id in dev_users else "start"
    keyboard = [
        [InlineKeyboardButton("📋 View My Jobs", callback_data="emp_view_jobs")],
        [InlineKeyboardButton("Back", callback_data=back_callback)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = "👷 Employee Dashboard (Dev View):"
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    back_callback = "dev_dashboard" if update.effective_user.id in dev_users else "start"
    now = datetime.now()
    header = f"Director's Desk (Dev View) - {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
    keyboard = [
        [InlineKeyboardButton("📝 Assign Jobs", callback_data="dir_assign_jobs_0")],
        [InlineKeyboardButton("👤 View Andy's Jobs (Today)", callback_data="view_andys_jobs")],
        [InlineKeyboardButton("👤 View Alex's Jobs (Today)", callback_data="view_alexs_jobs")],
        [InlineKeyboardButton("Calendar", callback_data="calendar_view")],
        [InlineKeyboardButton("Back", callback_data=back_callback)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, header, reply_markup=markup)
    else:
        await update.message.reply_text(header, reply_markup=markup)

#######################################
# DIRECTOR DASHBOARD - MAIN VIEW
#######################################

async def director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    header = f"Director's Desk - {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
    if update.effective_user.id in dev_users:
        keyboard = [
            [InlineKeyboardButton("📝 Assign Jobs", callback_data="dir_assign_jobs_0")],
            [InlineKeyboardButton("👤 View Andy's Jobs (Today)", callback_data="view_andys_jobs")],
            [InlineKeyboardButton("👤 View Alex's Jobs (Today)", callback_data="view_alexs_jobs")],
            [InlineKeyboardButton("Calendar", callback_data="calendar_view")],
            [InlineKeyboardButton("Back", callback_data="dev_dashboard")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Assign Jobs", callback_data="dir_assign_jobs_0")],
            [InlineKeyboardButton("👤 View Andy's Jobs (Today)", callback_data="view_andys_jobs")],
            [InlineKeyboardButton("👤 View Alex's Jobs (Today)", callback_data="view_alexs_jobs")],
            [InlineKeyboardButton("Calendar", callback_data="calendar_view")]
        ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, header, reply_markup=markup)
    else:
        await update.message.reply_text(header, reply_markup=markup)

#######################################
# DIRECTOR: View Employee Jobs for Today
#######################################

async def director_view_employee_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE, employee_id: int, employee_name: str):
    # Query jobs assigned to the employee that are scheduled for today.
    cursor.execute(
        "SELECT id, site_name, start_time, finish_time, status FROM grounds_data WHERE assigned_to = ? AND (start_time IS NULL OR DATE(start_time) = DATE('now', 'localtime'))",
        (employee_id,)
    )
    jobs = cursor.fetchall()
    if not jobs:
        await safe_edit_text(update.callback_query.message, f"No jobs for {employee_name} today.")
        return
    text = f"Jobs for {employee_name} (Today):\n"
    keyboard = []
    for job_id, site_name, start_time, finish_time, status in jobs:
        duration_str = "N/A"
        if start_time and finish_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                finish_dt = datetime.fromisoformat(finish_time)
                duration = finish_dt - start_dt
                duration_str = str(duration).split('.')[0]
            except Exception as e:
                duration_str = "N/A"
        button_text = f"{site_name} ({status.capitalize()} - {duration_str})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"send_job_{job_id}")])
        text += f"Job {job_id}: {site_name} - Status: {status.capitalize()} Duration: {duration_str}\n"
    keyboard.append([InlineKeyboardButton("Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update.callback_query.message, text, reply_markup=markup)

async def director_view_andys_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await director_view_employee_jobs(update, context, 1672989849, "Andy")

async def director_view_alexs_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await director_view_employee_jobs(update, context, 6396234665, "Alex")

#######################################
# DIRECTOR: View Job Details, Photos & Edit Note
#######################################

async def director_send_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, photos, start_time, finish_time, notes FROM grounds_data WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        await safe_edit_text(update.callback_query.message, f"Job {job_id} not found.")
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
    detail_text = f"📸 Job {job_id}: {site_name}\nDuration: {duration_str}\nNote: {notes if notes else 'None'}"
    keyboard = [
        [InlineKeyboardButton("Add/Edit Note", callback_data=f"edit_note_{job_id}")],
        [InlineKeyboardButton("Cancel Note Edit", callback_data=f"cancel_note_{job_id}")],
        [InlineKeyboardButton("Back", callback_data="director_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if media_group:
        try:
            if len(media_group) == 1:
                await update.callback_query.message.reply_photo(photo=media_group[0].media, caption=detail_text, reply_markup=markup)
            else:
                await update.callback_query.message.reply_media_group(media=media_group)
                await update.callback_query.message.reply_text(detail_text, reply_markup=markup)
        except Exception as e:
            await update.callback_query.message.reply_text(f"📸 Error sending photos for Job {job_id}: {str(e)}")
            logger.error(f"Send media group error for Job {job_id}: {str(e)}")
    else:
        await update.callback_query.message.reply_text(detail_text, reply_markup=markup)

async def director_edit_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["awaiting_note_for"] = job_id
    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data=f"cancel_note_{job_id}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update.callback_query.message, f"Please send the note for Job {job_id}:", reply_markup=markup)

async def director_cancel_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    # Return to job detail view
    await director_send_job(update, context)

#######################################
# DIRECTOR: Other Features (Assign, Batch Notes)
#######################################

async def director_assign_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.callback_query.data.startswith("dir_assign_jobs_"):
        try:
            page = int(update.callback_query.data.split("_")[-1])
        except ValueError:
            page = 0
        context.user_data["current_page"] = page
    else:
        page = context.user_data.get("current_page", 0)
    text, markup = build_director_assign_jobs_page(page, context)
    try:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    except BadRequest as e:
        logger.error(f"Edit failed: {str(e)} - Falling back to reply_text")
        await update.callback_query.message.reply_text(text, reply_markup=markup)

async def director_add_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_jobs = context.user_data.get("selected_jobs", set())
    if not selected_jobs:
        await safe_edit_text(update.callback_query.message, "⚠️ No jobs selected.")
        return
    await safe_edit_text(update.callback_query.message, "📝 Type your notes for the selected jobs:")
    context.user_data["awaiting_notes"] = True

async def handle_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_notes" in context.user_data and context.user_data["awaiting_notes"]:
        notes = update.message.text
        selected_jobs = context.user_data.get("selected_jobs", set())
        for site_name in selected_jobs:
            cursor.execute("SELECT id FROM grounds_data WHERE site_name = ?", (site_name,))
            job = cursor.fetchone()
            if job:
                cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (notes, job[0]))
        conn.commit()
        await update.message.reply_text(f"✅ Notes added to {len(selected_jobs)} job(s).")
        del context.user_data["awaiting_notes"]
        await director_assign_jobs(update, context)

async def assign_employee_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_jobs = context.user_data.get("selected_jobs", set())
    logger.info(f"Assign submenu - selected_jobs: {selected_jobs}")
    if not selected_jobs:
        await safe_edit_text(update.callback_query.message, "⚠️ No jobs selected.")
        return
    keyboard = [
        [InlineKeyboardButton("Andy", callback_data="assign_to_1672989849")],
        [InlineKeyboardButton("Alex", callback_data="assign_to_6396234665")],
        [InlineKeyboardButton("Back", callback_data="dir_assign_jobs_0")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    job_list = ", ".join(selected_jobs)
    await safe_edit_text(update.callback_query.message, f"✅ Selected Jobs: {job_list}\nChoose an employee:", reply_markup=markup)

async def assign_jobs_to_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employee_id = int(update.callback_query.data.split("_")[-1])
    selected_jobs = context.user_data.get("selected_jobs", set())
    logger.info(f"Assigning to {employee_id} - selected_jobs: {selected_jobs}")
    if not selected_jobs:
        await safe_edit_text(update.callback_query.message, "⚠️ No jobs selected.")
        return
    for site_name in selected_jobs:
        cursor.execute("SELECT id FROM grounds_data WHERE site_name = ?", (site_name,))
        job = cursor.fetchone()
        if job:
            cursor.execute("UPDATE grounds_data SET assigned_to = ?, status = 'pending' WHERE id = ?", (employee_id, job[0]))
            logger.info(f"Assigned {site_name} to {employee_id}")
        else:
            logger.error(f"Site {site_name} not found in grounds_data")
    conn.commit()
    job_list = ", ".join(selected_jobs)
    employee_name = employee_users.get(employee_id, "Unknown")
    await safe_edit_text(update.callback_query.message, f"✅ Assigned {job_list} to {employee_name}.")
    context.user_data["selected_jobs"].clear()
    await director_dashboard(update, context)

#######################################
# EMPLOYEE DASHBOARD & FEATURES
#######################################

async def emp_employee_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_photo_for" in context.user_data:
        del context.user_data["awaiting_photo_for"]
    back_callback = "dev_dashboard" if update.effective_user.id in dev_users else "start"
    keyboard = [
        [InlineKeyboardButton("📋 View My Jobs", callback_data="emp_view_jobs")],
        [InlineKeyboardButton("Back", callback_data=back_callback)]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = "👷 Employee Dashboard:"
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup)

async def emp_view_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT id, site_name, area, status FROM grounds_data WHERE assigned_to = ? AND (start_time IS NULL OR DATE(start_time) = DATE('now', 'localtime'))", (user_id,))
    jobs = cursor.fetchall()
    if not jobs:
        if update.callback_query:
            await safe_edit_text(update.callback_query.message, "📋 You have no assigned jobs today.")
        elif update.message:
            await update.message.reply_text("📋 You have no assigned jobs today.")
        return
    keyboard = []
    for job_id, site_name, area, status in jobs:
        prefix = "✅ " if status == "completed" else "▶️ " if status == "in_progress" else "📌 "
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix}{site_name} ({area or 'No Area'}) [{status.capitalize()}]",
                callback_data=f"job_menu_{job_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("Back", callback_data="emp_employee_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, "📋 Your Jobs (Today):", reply_markup=markup)
    elif update.message:
        await update.message.reply_text("📋 Your Jobs (Today):", reply_markup=markup)

async def emp_job_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, status, notes FROM grounds_data WHERE id = ?", (job_id,))
    site_name, status, notes = cursor.fetchone()
    keyboard = [
        [InlineKeyboardButton("▶️ Start Job", callback_data=f"start_job_{job_id}"),
         InlineKeyboardButton("⏹️ Finish Job", callback_data=f"finish_job_{job_id}")],
        [InlineKeyboardButton("📸 Upload Photo", callback_data=f"upload_photo_{job_id}"),
         InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}")],
        [InlineKeyboardButton("Add/Edit Note", callback_data=f"edit_note_{job_id}")],
        [InlineKeyboardButton("🗺️ Map Link", callback_data=f"map_link_{job_id}"),
         InlineKeyboardButton("Back", callback_data="emp_view_jobs")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    notes_text = f"\nNotes: {notes}" if notes else "\nNotes: None"
    text = f"Job: {site_name}\nStatus: {status.capitalize()}{notes_text}"
    try:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    except BadRequest as e:
        logger.error(f"Failed to edit message in emp_job_menu for Job {job_id}: {str(e)}")
        await update.callback_query.message.reply_text(text, reply_markup=markup)

async def emp_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    await update.callback_query.message.edit_text(f"📸 Please send a photo for Job {job_id}.")
    context.user_data["awaiting_photo_for"] = job_id

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
    current = cursor.fetchone()[0]
    if current and current.strip():
        new_photos = current.strip() + "|" + photo_path
    else:
        new_photos = photo_path
    cursor.execute("UPDATE grounds_data SET photos = ? WHERE id = ?", (new_photos, job_id))
    conn.commit()
    logger.info(f"Photo saved for Job {job_id}: {photo_path}")
    msg = await update.message.reply_text(f"✅ Photo uploaded for Job {job_id}.")
    await asyncio.sleep(2)
    await msg.delete()
    await emp_view_jobs(update, context)

async def emp_site_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, contact, gate_code FROM grounds_data WHERE id = ?", (job_id,))
    site_name, contact, gate_code = cursor.fetchone()
    info_text = f"Contact: {contact}\nGate Code: {gate_code}"
    cursor.execute("SELECT status, notes FROM grounds_data WHERE id = ?", (job_id,))
    status, notes = cursor.fetchone()
    keyboard = [
        [InlineKeyboardButton("▶️ Start Job", callback_data=f"start_job_{job_id}"),
         InlineKeyboardButton("⏹️ Finish Job", callback_data=f"finish_job_{job_id}")],
        [InlineKeyboardButton("📸 Upload Photo", callback_data=f"upload_photo_{job_id}"),
         InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}")],
        [InlineKeyboardButton("🗺️ Map Link", callback_data=f"map_link_{job_id}"),
         InlineKeyboardButton("Back", callback_data="emp_view_jobs")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    notes_text = f"\nNotes: {notes}" if notes else "\nNotes: None"
    await safe_edit_text(update.callback_query.message, f"Job: {site_name}\nStatus: {status.capitalize()}{notes_text}\n{info_text}", reply_markup=markup)

async def emp_start_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("UPDATE grounds_data SET status = 'in_progress', start_time = ? WHERE id = ?",
                   (datetime.now().isoformat(), job_id))
    conn.commit()
    await safe_edit_text(update.callback_query.message, f"▶️ Job {job_id} started.")
    await emp_view_jobs(update, context)

async def emp_finish_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("UPDATE grounds_data SET status = 'completed', finish_time = ? WHERE id = ?",
                   (datetime.now().isoformat(), job_id))
    conn.commit()
    await safe_edit_text(update.callback_query.message, f"⏹️ Job {job_id} finished.")
    await emp_view_jobs(update, context)

async def emp_map_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    cursor.execute("SELECT site_name, map_link FROM grounds_data WHERE id = ?", (job_id,))
    site_name, map_link = cursor.fetchone()
    map_text = f"Map: {map_link}" if map_link else "No map available."
    cursor.execute("SELECT status, notes FROM grounds_data WHERE id = ?", (job_id,))
    status, notes = cursor.fetchone()
    keyboard = [
        [InlineKeyboardButton("▶️ Start Job", callback_data=f"start_job_{job_id}"),
         InlineKeyboardButton("⏹️ Finish Job", callback_data=f"finish_job_{job_id}")],
        [InlineKeyboardButton("📸 Upload Photo", callback_data=f"upload_photo_{job_id}"),
         InlineKeyboardButton("ℹ️ Site Info", callback_data=f"site_info_{job_id}")],
        [InlineKeyboardButton("🗺️ Map Link", callback_data=f"map_link_{job_id}"),
         InlineKeyboardButton("Back", callback_data="emp_view_jobs")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    notes_text = f"\nNotes: {notes}" if notes else "\nNotes: None"
    await safe_edit_text(update.callback_query.message, f"Job: {site_name}\nStatus: {status.capitalize()}{notes_text}\n{map_text}", reply_markup=markup)

#######################################
# NOTE EDITING FUNCTIONALITY FOR DIRECTOR
#######################################

async def director_edit_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["awaiting_note_for"] = job_id
    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data=f"cancel_note_{job_id}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_text(update.callback_query.message, f"Please send the note for Job {job_id}:", reply_markup=markup)

async def director_cancel_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simply return to the job detail view.
    await director_send_job(update, context)

#######################################
# TEXT HANDLER (Note Editing & Others)
#######################################

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_note_for" in context.user_data:
        job_id = context.user_data.pop("awaiting_note_for")
        note = update.message.text
        cursor.execute("UPDATE grounds_data SET notes = ? WHERE id = ?", (note, job_id))
        conn.commit()
        await update.message.reply_text(f"Note updated for Job {job_id}.")
        return
    if "awaiting_notes" in context.user_data and context.user_data["awaiting_notes"]:
        await handle_notes(update, context)

#######################################
# CALLBACK QUERY HANDLER
#######################################

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "start":
        await start(update, context)
    elif data == "dev_employee_dashboard":
        await dev_employee_dashboard(update, context)
    elif data == "dev_director_dashboard":
        await dev_director_dashboard(update, context)
    elif data == "view_andys_jobs":
        await director_view_andys_jobs(update, context)
    elif data == "view_alexs_jobs":
        await director_view_alexs_jobs(update, context)
    elif data == "calendar_view":
        await director_calendar_view(update, context)
    elif data.startswith("select_day_"):
        await director_select_day(update, context)
    elif data.startswith("dir_assign_jobs_"):
        await director_assign_jobs(update, context)
    elif data == "director_dashboard":
        await director_dashboard(update, context)
    elif data == "assign_selected_jobs":
        await assign_employee_submenu(update, context)
    elif data.startswith("toggle_job_"):
        site_name = data.split("_", 2)[-1]
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
    elif data.startswith("assign_to_"):
        await assign_jobs_to_employee(update, context)
    elif data == "emp_view_jobs":
        await emp_view_jobs(update, context)
    elif data.startswith("job_menu_"):
        await emp_job_menu(update, context)
    elif data == "emp_employee_dashboard":
        await emp_employee_dashboard(update, context)
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
    elif data == "add_notes":
        await director_add_notes(update, context)
    elif data.startswith("send_job_"):
        await director_send_job(update, context)
    elif data.startswith("edit_note_"):
        await director_edit_note(update, context)
    elif data.startswith("cancel_note_"):
        await director_cancel_note(update, context)
    elif data == "noop":
        pass

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
        text = "🚫 You do not have a registered role."
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
        "- *Director*: View/assign jobs, add/edit individual notes, view detailed job info (times and photos), and use the Calendar for weekly scheduling.\n"
        "- *Employee*: View your assigned jobs (only today’s), start/finish jobs, and upload photos.\n"
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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(callback_handler))
    scheduler = AsyncIOScheduler(event_loop=loop)
    scheduler.add_job(reset_completed_jobs, 'cron', hour=0, minute=0)
    scheduler.start()
    application.run_polling()

if __name__ == "__main__":
    main()
