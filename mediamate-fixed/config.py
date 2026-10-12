import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
WEB_APP_URL = os.getenv('WEB_APP_URL', '').strip().rstrip('/')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '').strip()
ADMIN_USER_IDS = {int(x) for x in os.getenv('ADMIN_USER_IDS', '').split(',') if x.strip().isdigit()}

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is missing')
if not WEBHOOK_SECRET or WEBHOOK_SECRET == 'change-me':
    raise RuntimeError('WEBHOOK_SECRET must be set to a random secret')
