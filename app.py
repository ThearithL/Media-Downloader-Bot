import asyncio
import logging
import threading

from flask import Flask, jsonify, render_template, request
from telegram import Update

from bot import build_app
from config import BOT_TOKEN, WEB_APP_URL, WEBHOOK_SECRET
from downloader import analyze

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediamate")

web = Flask(__name__)
tg = build_app()
loop = asyncio.new_event_loop()
ready = threading.Event()


def runner():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(tg.initialize())
        loop.run_until_complete(tg.start())
        ready.set()
        logger.info("Telegram application initialized")
        loop.run_forever()
    except Exception:
        logger.exception("Telegram application failed to start")


threading.Thread(target=runner, daemon=True).start()


@web.get("/")
def index():
    return render_template("index.html")


@web.get("/health")
def health():
    return jsonify(ok=True, telegram_ready=ready.is_set())


@web.get("/health/telegram")
def telegram_health():
    if not BOT_TOKEN:
        return jsonify(ok=False, error="BOT_TOKEN is missing"), 500
    if not ready.wait(timeout=5):
        return jsonify(ok=False, error="Telegram application is not ready"), 503
    try:
        future = asyncio.run_coroutine_threadsafe(tg.bot.get_webhook_info(), loop)
        info = future.result(timeout=15)
        return jsonify(
            ok=True,
            webhook_url=info.url or "",
            expected_webhook=f"{WEB_APP_URL}/telegram/webhook" if WEB_APP_URL else "",
            pending_update_count=info.pending_update_count,
            last_error_message=info.last_error_message or "",
            last_error_date=info.last_error_date.isoformat() if info.last_error_date else None,
        )
    except Exception:
        logger.exception("Could not read webhook info")
        return jsonify(ok=False, error="Could not read Telegram webhook info"), 500


@web.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(error="Invalid URL"), 400
    try:
        return jsonify(analyze(url))
    except Exception:
        logger.exception("Analyze failed")
        return jsonify(error="Unsupported/private/unavailable URL"), 400


@web.post("/telegram/webhook")
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != WEBHOOK_SECRET:
        logger.warning("Rejected Telegram webhook: secret mismatch")
        return "forbidden", 403
    if not ready.is_set():
        return "telegram application not ready", 503
    try:
        update = Update.de_json(request.get_json(force=True), tg.bot)
        future = asyncio.run_coroutine_threadsafe(tg.process_update(update), loop)
        future.result(timeout=20)
        return "ok", 200
    except Exception:
        logger.exception("Telegram update processing failed")
        return "processing failed", 500


def set_webhook():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing")
        return
    if not WEB_APP_URL:
        logger.error("WEB_APP_URL is missing")
        return
    if not WEBHOOK_SECRET or WEBHOOK_SECRET == "change-me":
        logger.error("WEBHOOK_SECRET is missing or insecure")
        return
    if not ready.wait(timeout=20):
        logger.error("Telegram application did not become ready")
        return

    webhook_url = f"{WEB_APP_URL}/telegram/webhook"
    try:
        future = asyncio.run_coroutine_threadsafe(
            tg.bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=False,
                allowed_updates=Update.ALL_TYPES,
            ),
            loop,
        )
        future.result(timeout=20)
        logger.info("Webhook configured: %s", webhook_url)
    except Exception:
        logger.exception("Webhook setup failed")


threading.Thread(target=set_webhook, daemon=True).start()

app = web
