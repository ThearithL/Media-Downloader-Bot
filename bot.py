import asyncio
import json
import logging
import os
import shutil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from config import BOT_TOKEN, WEB_APP_URL
from downloader import analyze, download

logger = logging.getLogger("mediamate.bot")

MENU = [['📥 Download','🎵 MP3'],['🎬 MP4','🖼️ Image'],['📜 History','⭐ Favorites'],['📊 Statistics','🌐 Language'],['⚙️ Settings','❓ Help']]


def home_keyboard():
    rows = [[InlineKeyboardButton(x, callback_data='menu:' + x) for x in row] for row in MENU]
    if WEB_APP_URL:
        rows.append([InlineKeyboardButton('📱 Open Mini App', web_app=WebAppInfo(WEB_APP_URL))])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        'សួស្តី 👋\nផ្ញើ public media link ដែលអ្នកមានសិទ្ធិទាញយក ឬបើក Mini App។\n\nSend an authorized public media link to analyze it.',
        reply_markup=home_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        '🔗 Paste a supported public URL. I will show metadata and available quality.\n'
        '🎬 MP4 / 🎵 MP3 are available when the source permits extraction.\n'
        '🔒 Private/DRM-protected content is not bypassed.'
    )


async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    name = q.data.split(':', 1)[1]
    texts = {
        '📥 Download':'ផ្ញើ Link មកខ្ញុំ ដើម្បី Analyze និង Download។',
        '🎵 MP3':'ផ្ញើ Link ហើយជ្រើស 🎵 MP3។',
        '🎬 MP4':'ផ្ញើ Link ហើយជ្រើស quality។',
        '🖼️ Image':'Thumbnail នឹងបង្ហាញបើ source មាន។',
        '📜 History':'History មាននៅក្នុង Mini App។',
        '⭐ Favorites':'Favorites មាននៅក្នុង Mini App។',
        '📊 Statistics':'Statistics នឹងបន្ថែមនៅ version បន្ទាប់។',
        '🌐 Language':'Mini App supports Khmer + English settings.',
        '⚙️ Settings':'Settings មាននៅក្នុង Mini App។',
        '❓ Help':'ផ្ញើ /help សម្រាប់ជំនួយ។',
    }
    await q.message.reply_text(texts.get(name, name))


async def analyze_and_reply(message, context, url):
    msg = await message.reply_text('🔍 កំពុងពិនិត្យ Link...')
    try:
        data = await asyncio.to_thread(analyze, url)
        context.user_data['url'] = url
        qs = data.get('qualities', [])[:5] or [720, 480, 360]
        rows = [[InlineKeyboardButton(f'🎬 {q}p', callback_data=f'dl:mp4:{q}') for q in qs[:3]]]
        if len(qs) > 3:
            rows.append([InlineKeyboardButton(f'🎬 {q}p', callback_data=f'dl:mp4:{q}') for q in qs[3:]])
        rows.append([InlineKeyboardButton('🎵 MP3', callback_data='dl:mp3:192')])
        dur = data.get('duration')
        duration = f'{dur//60}:{dur%60:02d}' if isinstance(dur, int) else '—'
        text = f"✅ Link Detected\n\n🎬 {data.get('title','Media')}\n🌐 {data.get('extractor') or 'Media'}\n⏱ {duration}\n\nជ្រើស format / quality:"
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(rows))
        if data.get('thumbnail'):
            try:
                await message.reply_photo(data['thumbnail'])
            except Exception:
                logger.warning('Could not send thumbnail', exc_info=True)
    except Exception as exc:
        logger.exception('Analyze failed for URL: %s', url)
        detail = str(exc)
        if 'Sign in' in detail or 'cookies' in detail.lower():
            text = '❌ Source នេះត្រូវការ login/cookies។ Bot មិនអាច bypass private/restricted media បានទេ។'
        elif 'player response' in detail.lower():
            text = '❌ YouTube បានផ្លាស់ប្តូរ player response។ សូមសាកម្តងទៀត ឬ link ផ្សេង។'
        else:
            text = '❌ មិនអាច Analyze Link នេះបានទេ។ Link អាច private, unsupported ឬ source បានផ្លាស់ប្តូរ។'
        await msg.edit_text(text)


async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.effective_message.text or '').strip()
    if url.startswith(('http://', 'https://')):
        await analyze_and_reply(update.effective_message, context, url)


async def webapp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    raw = message.web_app_data.data if message and message.web_app_data else ''
    try:
        data = json.loads(raw)
    except Exception:
        return await message.reply_text('❌ Invalid Mini App request.')

    url = str(data.get('url', '')).strip()
    kind = str(data.get('kind', 'mp4')).lower()
    if not url.startswith(('http://', 'https://')):
        return await message.reply_text('❌ Invalid URL from Mini App.')

    context.user_data['url'] = url
    if data.get('action') == 'download' and kind in {'mp3', 'mp4'}:
        # Analyze first so the user gets safe format/quality choices. For MP3,
        # immediately expose the normal download callback after analysis.
        await analyze_and_reply(message, context, url)
    else:
        await analyze_and_reply(message, context, url)


async def dl_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    url = context.user_data.get('url')
    if not url:
        return await q.message.reply_text('សូមផ្ញើ Link ម្តងទៀត។')
    _, kind, quality = q.data.split(':')
    status = await q.message.reply_text('⚙️ Processing...')
    outdir = None
    try:
        path, outdir = await asyncio.to_thread(download, url, kind, quality)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        size = os.path.getsize(path)
        if size > 49 * 1024 * 1024:
            return await status.edit_text('⚠️ File ធំពេកសម្រាប់ Telegram upload limit ដែល project នេះកំណត់ (49 MB)។ សូមជ្រើស quality ទាបជាង។')
        with open(path, 'rb') as f:
            if kind == 'mp3':
                await q.message.reply_audio(f, caption='✅ Done')
            else:
                await q.message.reply_video(f, caption='✅ Done', supports_streaming=True)
        await status.delete()
    except Exception:
        logger.exception('Download failed: kind=%s quality=%s url=%s', kind, quality, url)
        await status.edit_text('❌ Download/convert failed. សូមសាក quality ផ្សេង ឬ link ផ្សេង។')
    finally:
        if outdir:
            shutil.rmtree(outdir, ignore_errors=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        # Render zero-downtime deploys can briefly overlap old/new instances.
        # PTB retries polling automatically after the old instance exits.
        logger.warning('Temporary Telegram getUpdates conflict during deploy; retrying.')
        return
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning('Temporary Telegram network error: %s', err)
        return
    logger.exception('Unhandled Telegram error', exc_info=err)


def build_app():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CallbackQueryHandler(dl_cb, pattern=r'^dl:'))
    app.add_handler(CallbackQueryHandler(menu_cb, pattern=r'^menu:'))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_handler))
    app.add_error_handler(error_handler)
    return app
