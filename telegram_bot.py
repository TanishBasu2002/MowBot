######################################################
# TELEGRAM_BOT.PY (ULTIMATE VERSION V7 - ENHANCED MowBot MVP)
#
# Features:
# - Photo Upload Enhancement: Splits media groups into chunks of 10 (up to 25 photos).
# - Job Assignment Improvements: Adds a day-of-the-week selection step and groups jobs by day.
# - Inline UI Enhancements: Dynamic greetings, sleek inline menus with clear navigation.
# - Editing Assigned Jobs: Director can toggle green tick selections to modify assignments.
# - Core functionalities and robust error handling remain intact.
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

#####################
# ENV & TOKEN SETUP
#####################

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Ensure your .env is in /root/CHATBOT

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#####################
# ROLES & USERS
#####################

dev_users = {1672989849}                # Dev (and Andy/Director)
director_users = {1672989849, 7996550019, 8018680694}  # Directors
employee_users = {1672989849: "Andy", 6396234665: "Alex"}  # Updated: Alex's ID is now 6396234665

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
        scheduled_date TEXT  -- New column to store the day assignment (e.g., 'Monday')
    );
    """
)
cursor.executescript(""" 
    CREATE INDEX IF NOT EXISTS idx_grounds_assigned_to ON grounds_data(assigned_to);
    CREATE INDEX IF NOT EXISTS idx_grounds_status ON grounds_data(status);
    CREATE INDEX IF NOT EXISTS idx_grounds_site_name ON grounds_data(site_name);
""")
# (Assume initial population has been done previously)

#######################################
# HELPER: Safe Edit Text Function
#######################################

async def safe_edit_text(message, text, reply_markup=None):
    """Attempt to edit a message; if it fails (e.g., message has no text), send a new message."""
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
    # Reset jobs completed yesterday (only reset those that are for 'today'; preserve scheduled future jobs)
    cursor.execute("UPDATE grounds_data SET status = 'pending', assigned_to = NULL, finish_time = NULL WHERE status = 'completed' AND (scheduled_date IS NULL OR scheduled_date = date('now','localtime'))")
    conn.commit()

#######################################
# PHOTO UPLOAD ENHANCEMENT (in director_send_job)
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
        # Split media_group into chunks of 10
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

#######################################
# JOB ASSIGNMENT & DAY SELECTION
#######################################

async def director_select_day_for_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display an inline keyboard for selecting a day of the week for assignment."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    keyboard = []
    for day in days:
        keyboard.append([InlineKeyboardButton(day, callback_data=f"assign_day_{day}")])
    # Include a Back button to return to the main director dashboard.
    keyboard.append([InlineKeyboardButton("Back", callback_data="director_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    
    # Dynamic greeting based on time
    current_hour = datetime.now().hour
    greeting = "Good Morning" if current_hour < 12 else "Good Afternoon"
    header = f"{greeting}! Please select a day of the week for assignment:"
    await safe_edit_text(update.callback_query.message, header, reply_markup=markup)

async def director_assign_day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the selected day and move to employee assignment submenu."""
    selected_day = update.callback_query.data.split("_")[-1]
    # Store the selected day in user_data for later use.
    context.user_data["selected_day"] = selected_day
    # Now move to the employee assignment submenu.
    keyboard = [
        [InlineKeyboardButton("Assign to Andy", callback_data="assign_to_1672989849")],
        [InlineKeyboardButton("Assign to Alex", callback_data="assign_to_6396234665")],
        [InlineKeyboardButton("Back", callback_data="director_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    message = f"You selected {selected_day}. Please choose an employee to assign the selected jobs."
    await safe_edit_text(update.callback_query.message, message, reply_markup=markup)

#######################################
# DIRECTOR DASHBOARD (with Dynamic Greetings)
#######################################

async def director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    current_hour = now.hour
    greeting = "Good Morning" if current_hour < 12 else "Good Afternoon"
    header = f"{greeting}, Director! \nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
    # Build dashboard buttons: Assign Jobs, View Jobs by Day, Calendar
    keyboard = [
        [InlineKeyboardButton("📝 Assign Jobs", callback_data="dir_assign_jobs_0")],
        [InlineKeyboardButton("👤 View Andy's Jobs", callback_data="view_andys_jobs")],
        [InlineKeyboardButton("👤 View Alex's Jobs", callback_data="view_alexs_jobs")],
        [InlineKeyboardButton("Calendar", callback_data="calendar_view")]
    ]
    # If the user is a dev, add a dev-back button
    if update.effective_user.id in dev_users:
        keyboard.append([InlineKeyboardButton("Back", callback_data="dev_dashboard")])
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, header, reply_markup=markup)
    else:
        await update.message.reply_text(header, reply_markup=markup)

#######################################
# DIRECTOR: View Employee Jobs (Grouped by Day)
#######################################

async def director_view_employee_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE, employee_id: int, employee_name: str):
    # Query jobs assigned to the employee, grouping by scheduled_date (or if null, assume today)
    cursor.execute(
        """
        SELECT id, site_name, scheduled_date, start_time, finish_time, status 
        FROM grounds_data 
        WHERE assigned_to = ? AND (scheduled_date IS NULL OR DATE(scheduled_date) = DATE('now','localtime'))
        ORDER BY scheduled_date, id
        """,
        (employee_id,)
    )
    jobs = cursor.fetchall()
    if not jobs:
        await safe_edit_text(update.callback_query.message, f"No jobs for {employee_name} today.")
        return
    text = f"Jobs for {employee_name}:\n"
    keyboard = []
    current_day = None
    for job_id, site_name, scheduled_date, start_time, finish_time, status in jobs:
        # Use scheduled_date if available; otherwise, default to today.
        day = scheduled_date if scheduled_date else "Today"
        if day != current_day:
            current_day = day
            text += f"\n--- {current_day} ---\n"
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
# DIRECTOR: Other Features (Assign Jobs & Batch Notes)
#######################################

async def director_assign_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # For assigning jobs, assume the Director selects jobs via green ticks.
    # After job selection, if the Director clicks "Continue", prompt to select a day.
    if update.callback_query and update.callback_query.data.startswith("dir_assign_jobs_"):
        try:
            page = int(update.callback_query.data.split("_")[-1])
        except ValueError:
            page = 0
        context.user_data["current_page"] = page
    else:
        page = context.user_data.get("current_page", 0)
    text, markup = build_director_assign_jobs_page(page, context)
    # Add an extra button for "Continue" that leads to day selection if jobs are selected.
    if context.user_data.get("selected_jobs"):
        extra_button = [InlineKeyboardButton("Continue to Day Selection", callback_data="select_day_for_assignment")]
        markup.inline_keyboard.append(extra_button)
    try:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    except BadRequest as e:
        logger.error(f"Error in director_assign_jobs: {str(e)}")
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
        [InlineKeyboardButton("Assign to Andy", callback_data="assign_to_1672989849")],
        [InlineKeyboardButton("Assign to Alex", callback_data="assign_to_6396234665")],
        [InlineKeyboardButton("Back", callback_data="director_dashboard")]
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
    # Update each selected job with the employee and the selected day
    selected_day = context.user_data.get("selected_day", "Today")
    for site_name in selected_jobs:
        cursor.execute("SELECT id FROM grounds_data WHERE site_name = ?", (site_name,))
        job = cursor.fetchone()
        if job:
            cursor.execute("UPDATE grounds_data SET assigned_to = ?, status = 'pending', scheduled_date = ? WHERE id = ?", (employee_id, selected_day, job[0]))
            logger.info(f"Assigned {site_name} to {employee_id} for {selected_day}")
        else:
            logger.error(f"Site {site_name} not found in grounds_data")
    conn.commit()
    job_list = ", ".join(selected_jobs)
    employee_name = employee_users.get(employee_id, "Unknown")
    await safe_edit_text(update.callback_query.message, f"✅ Assigned {job_list} to {employee_name} for {selected_day}.")
    context.user_data["selected_jobs"].clear()
    context.user_data.pop("selected_day", None)
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
    # Return to the job detail view.
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
    elif data == "select_day_for_assignment":
        await director_select_day_for_assignment(update, context)
    elif data.startswith("assign_day_"):
        await director_assign_day_selected(update, context)
    elif data.startswith("dir_assign_jobs_"):
        await director_assign_jobs(update, context)
    elif data == "director_dashboard":
        await director_dashboard(update, context)
    elif data == "assign_selected_jobs":
        await director_select_day_for_assignment(update, context)
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
# DEV DASHBOARD FUNCTIONS
#######################################

async def dev_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Developer Dashboard: Choose an option"
    keyboard = [
        [InlineKeyboardButton("Director Dashboard", callback_data="dev_director_dashboard")],
        [InlineKeyboardButton("Employee Dashboard", callback_data="dev_employee_dashboard")],
        [InlineKeyboardButton("Back to Start", callback_data="start")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_director_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Developer Director Dashboard: Debug Info & Director Options"
    keyboard = [
        [InlineKeyboardButton("Director Dashboard", callback_data="director_dashboard")],
        [InlineKeyboardButton("Back to Dev Dashboard", callback_data="dev_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def dev_employee_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Developer Employee Dashboard: Debug Info & Employee Options"
    keyboard = [
        [InlineKeyboardButton("Employee Dashboard", callback_data="emp_employee_dashboard")],
        [InlineKeyboardButton("Back to Dev Dashboard", callback_data="dev_dashboard")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await safe_edit_text(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

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
