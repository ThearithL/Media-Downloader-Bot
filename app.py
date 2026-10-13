import logging
import threading

from flask import Flask, jsonify, render_template, request

from bot import build_app
from config import BOT_TOKEN
from downloader import analyze

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("mediamate")

web = Flask(__name__)
ready = threading.Event()
startup_error = {"message": ""}


def telegram_runner():
    """Run Telegram long polling in its own thread.

    This avoids the Flask/Gunicorn -> cross-thread asyncio webhook bridge that
    was accepting updates but intermittently leaving the PTB application in a
    not-ready state on Render.
    """
    if not BOT_TOKEN:
        startup_error["message"] = "BOT_TOKEN is missing"
        logger.error(startup_error["message"])
        return

    try:
        tg = build_app()

        async def on_start(application):
            # A bot cannot use getUpdates while a webhook is configured.
            # Remove the old webhook first, then polling owns update delivery.
            await application.bot.delete_webhook(drop_pending_updates=False)
            ready.set()
            logger.info("Telegram polling ready; webhook removed")

        tg.post_init = on_start
        tg.run_polling(
            allowed_updates=None,
            drop_pending_updates=False,
            close_loop=True,
            stop_signals=None,
        )
    except Exception as exc:
        startup_error["message"] = f"{type(exc).__name__}: {exc}"
        ready.clear()
        logger.exception("Telegram polling failed")


threading.Thread(target=telegram_runner, daemon=True, name="telegram-polling").start()


@web.get("/")
def index():
    return render_template("index.html")


@web.get("/health")
def health():
    return jsonify(
        ok=True,
        telegram_ready=ready.is_set(),
        telegram_mode="polling",
        telegram_error=startup_error["message"],
    )


@web.get("/health/telegram")
def telegram_health():
    status = 200 if ready.is_set() else 503
    return jsonify(
        ok=ready.is_set(),
        mode="polling",
        error=startup_error["message"],
    ), status


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


# Keep this endpoint during migration so stale Telegram webhook retries receive
# a successful response while delete_webhook propagates. New updates use polling.
@web.post("/telegram/webhook")
def retired_webhook():
    return "ok", 200


app = web
