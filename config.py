import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN=os.getenv('BOT_TOKEN','')
WEB_APP_URL=os.getenv('WEB_APP_URL','').rstrip('/')
WEBHOOK_SECRET=os.getenv('WEBHOOK_SECRET','change-me')
ADMIN_USER_IDS={int(x) for x in os.getenv('ADMIN_USER_IDS','').split(',') if x.strip().isdigit()}
