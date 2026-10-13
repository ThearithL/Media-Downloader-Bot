import asyncio
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
    """Run Telegram long polling in its own thread with an explicit event loop."""
    if not BOT_TOKEN:
        startup_error["message"] = "BOT_TOKEN is missing"
        logger.error(startup_error["message"])
        return

    # Python 3.12 does not automatically create an asyncio loop in a new
    # thread. python-telegram-bot run_polling() expects one to exist.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        tg = build_app()

        async def on_start(application):
            # getUpdates cannot run while a webhook is configured.
            await application.bot.delete_webhook(drop_pending_updates=False)
            ready.set()
            startup_error["message"] = ""
            logger.info("Telegram polling ready; webhook removed")

        tg.post_init = on_start
        tg.run_polling(
            allowed_updates=None,
            drop_pending_updates=False,
            close_loop=False,
            stop_signals=None,
        )
    except Exception as exc:
        startup_error["message"] = f"{type(exc).__name__}: {exc}"
        ready.clear()
        logger.exception("Telegram polling failed")
    finally:
        if not loop.is_closed():
            loop.close()


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


# Keep this endpoint temporarily so stale webhook retries receive 200 while
# delete_webhook propagates. New Telegram updates are handled by polling.
@web.post("/telegram/webhook")
def retired_webhook():
    return "ok", 200


app = web
