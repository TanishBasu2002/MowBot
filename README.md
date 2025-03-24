# MowBot - Telegram Bot for Lawn Maintenance

A professional Telegram bot for managing lawn maintenance jobs, employee assignments, and job tracking.

## Features

- Enhanced UI Components with professional message templates
- Photo upload support (up to 25 photos per job)
- Job assignment with day selection
- Employee job tracking
- Director dashboard with job management
- Developer mode for testing
- Daily job reset functionality
- Robust error handling

## Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd mowbot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your Telegram bot token:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

5. Run the bot:
```bash
python telegram_bot.py
```

## Server Deployment

1. SSH into your server:
```bash
ssh your_username@your_server_ip
```

2. Clone the repository:
```bash
git clone <your-repo-url>
cd mowbot
```

3. Set up Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. Create and edit the `.env` file:
```bash
nano .env
# Add your TELEGRAM_BOT_TOKEN
```

5. Set up systemd service (create `/etc/systemd/system/mowbot.service`):
```ini
[Unit]
Description=MowBot Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/mowbot
Environment=PYTHONPATH=/path/to/mowbot
ExecStart=/path/to/mowbot/venv/bin/python telegram_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

6. Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mowbot
sudo systemctl start mowbot
```

7. Check status:
```bash
sudo systemctl status mowbot
```

## Logs

View logs:
```bash
sudo journalctl -u mowbot -f
```

## Maintenance

- The bot automatically resets completed jobs at midnight
- Database backups are recommended
- Monitor logs for any issues

## Support

For support, contact your system administrator. 