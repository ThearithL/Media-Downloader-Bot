import os, threading, asyncio
from flask import Flask, render_template, request, jsonify
from bot import build_app
from config import WEB_APP_URL, WEBHOOK_SECRET
from downloader import analyze

web=Flask(__name__); tg=build_app(); loop=asyncio.new_event_loop()
def runner():
    asyncio.set_event_loop(loop); loop.run_until_complete(tg.initialize()); loop.run_until_complete(tg.start()); loop.run_forever()
threading.Thread(target=runner,daemon=True).start()

@web.get('/')
def index(): return render_template('index.html')
@web.get('/health')
def health(): return {'ok':True}
@web.post('/api/analyze')
def api_analyze():
    url=(request.json or {}).get('url','')
    if not url.startswith(('http://','https://')): return jsonify(error='Invalid URL'),400
    try: return jsonify(analyze(url))
    except Exception: return jsonify(error='Unsupported/private/unavailable URL'),400
@web.post('/telegram/webhook')
def telegram_webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token')!=WEBHOOK_SECRET: return 'forbidden',403
    from telegram import Update
    update=Update.de_json(request.get_json(force=True),tg.bot)
    asyncio.run_coroutine_threadsafe(tg.process_update(update),loop)
    return 'ok'

def set_webhook():
    if WEB_APP_URL:
        fut=asyncio.run_coroutine_threadsafe(tg.bot.set_webhook(f'{WEB_APP_URL}/telegram/webhook',secret_token=WEBHOOK_SECRET,drop_pending_updates=False),loop)
        try: fut.result(timeout=20)
        except Exception as e: print('Webhook setup:',e)
threading.Timer(3,set_webhook).start()
app=web
