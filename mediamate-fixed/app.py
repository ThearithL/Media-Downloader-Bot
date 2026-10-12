import asyncio
import logging
import threading
from flask import Flask, render_template, request, jsonify
from telegram import Update
from bot import build_app
from config import BOT_TOKEN, WEB_APP_URL, WEBHOOK_SECRET
from downloader import analyze

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
log = logging.getLogger('mediamate')

web = Flask(__name__)
tg = build_app()
loop = asyncio.new_event_loop()
ready = threading.Event()
startup_error = None


def bot_runner():
    global startup_error
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(tg.initialize())
        loop.run_until_complete(tg.start())
        if WEB_APP_URL:
            webhook_url = f"{WEB_APP_URL}/telegram/webhook"
            loop.run_until_complete(
                tg.bot.set_webhook(
                    url=webhook_url,
                    secret_token=WEBHOOK_SECRET,
                    drop_pending_updates=False,
                    allowed_updates=Update.ALL_TYPES,
                )
            )
            info = loop.run_until_complete(tg.bot.get_webhook_info())
            log.info('Telegram webhook active: %s', info.url)
        else:
            log.error('WEB_APP_URL is empty; webhook was not configured')
        ready.set()
        loop.run_forever()
    except Exception as exc:
        startup_error = f'{type(exc).__name__}: {exc}'
        log.exception('Telegram startup failed')
        ready.set()


threading.Thread(target=bot_runner, daemon=True, name='telegram-bot').start()


@web.get('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return jsonify(service='MediaMate', ok=True, mini_app=False)


@web.get('/health')
def health():
    return jsonify(ok=True, telegram_ready=ready.is_set() and startup_error is None)


@web.get('/health/telegram')
def telegram_health():
    if startup_error:
        return jsonify(ok=False, error=startup_error), 503
    if not ready.wait(timeout=1):
        return jsonify(ok=False, error='Telegram startup still in progress'), 503
    try:
        future = asyncio.run_coroutine_threadsafe(tg.bot.get_webhook_info(), loop)
        info = future.result(timeout=10)
        return jsonify(ok=True, webhook_url=info.url, pending_update_count=info.pending_update_count,
                       last_error_message=info.last_error_message or '')
    except Exception as exc:
        return jsonify(ok=False, error=f'{type(exc).__name__}: {exc}'), 503


@web.post('/api/analyze')
def api_analyze():
    url = (request.json or {}).get('url', '')
    if not url.startswith(('http://', 'https://')):
        return jsonify(error='Invalid URL'), 400
    try:
        return jsonify(analyze(url))
    except Exception:
        log.exception('Analyze failed')
        return jsonify(error='Unsupported/private/unavailable URL'), 400


@web.post('/telegram/webhook')
def telegram_webhook():
    if WEBHOOK_SECRET and request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        return 'forbidden', 403
    if startup_error or not ready.is_set():
        return 'telegram not ready', 503
    try:
        update = Update.de_json(request.get_json(force=True), tg.bot)
        future = asyncio.run_coroutine_threadsafe(tg.process_update(update), loop)
        future.result(timeout=20)
        return 'ok', 200
    except Exception:
        log.exception('Telegram update failed')
        return 'error', 500


app = web
