import asyncio
import json
import logging
import os
import shutil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, BotCommand
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


def persistent_menu():
    rows = [[KeyboardButton(x) for x in row] for row in MENU]
    if WEB_APP_URL:
        rows.append([KeyboardButton('📱 Open Mini App', web_app=WebAppInfo(WEB_APP_URL))])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True, input_field_placeholder='Paste a media link or choose a menu…')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        'សួស្តី 👋\nផ្ញើ public media link ដែលអ្នកមានសិទ្ធិទាញយក ឬជ្រើស Menu ខាងក្រោម។\n\nSend an authorized public media link or choose a menu.',
        reply_markup=persistent_menu(),
    )
    await update.effective_message.reply_text('⚡ Quick actions', reply_markup=home_keyboard())


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('📋 Main Menu / ម៉ឺនុយមេ', reply_markup=persistent_menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        '🔗 Paste a supported public URL. I will show metadata and available quality.\n'
        '🎬 MP4 / 🎵 MP3 are available when the source permits extraction.\n'
        '🔒 Private/DRM-protected content is not bypassed.',
        reply_markup=persistent_menu(),
    )


async def handle_menu_name(message, name):
    texts = {
        '📥 Download':'📥 ផ្ញើ Link មកខ្ញុំ ដើម្បី Analyze និង Download។',
        '🎵 MP3':'🎵 ផ្ញើ Link មកខ្ញុំ បន្ទាប់មកជ្រើស MP3។',
        '🎬 MP4':'🎬 ផ្ញើ Link មកខ្ញុំ ហើយជ្រើស video quality។',
        '🖼️ Image':'🖼️ Thumbnail នឹងបង្ហាញបើ source មាន។',
        '📜 History':'📜 History មាននៅក្នុង Mini App។',
        '⭐ Favorites':'⭐ Favorites មាននៅក្នុង Mini App។',
        '📊 Statistics':'📊 Statistics នឹងបន្ថែមនៅ version បន្ទាប់។',
        '🌐 Language':'🌐 Mini App supports Khmer + English settings.',
        '⚙️ Settings':'⚙️ Settings មាននៅក្នុង Mini App។',
        '❓ Help':'❓ ផ្ញើ /help សម្រាប់ជំនួយ។',
    }
    await message.reply_text(texts.get(name, name), reply_markup=persistent_menu())


async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await handle_menu_name(q.message, q.data.split(':', 1)[1])


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
        text = f"✅ Link Detected\n\n🎬 {data.get('title','Media')}\n🌐 {data.get('platform') or data.get('extractor') or 'Media'}\n⏱ {duration}\n\nជ្រើស format / quality:"
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


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or '').strip()
    if text in {item for row in MENU for item in row}:
        return await handle_menu_name(update.effective_message, text)
    if text.startswith(('http://', 'https://')):
        return await analyze_and_reply(update.effective_message, context, text)
    await update.effective_message.reply_text('🔗 សូមផ្ញើ media link ឬជ្រើស Menu ខាងក្រោម។', reply_markup=persistent_menu())


async def webapp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    raw = message.web_app_data.data if message and message.web_app_data else ''
    try:
        data = json.loads(raw)
    except Exception:
        return await message.reply_text('❌ Invalid Mini App request.')
    url = str(data.get('url', '')).strip()
    if not url.startswith(('http://', 'https://')):
        return await message.reply_text('❌ Invalid URL from Mini App.')
    context.user_data['url'] = url
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
            return await status.edit_text('⚠️ File ធំពេក (49 MB limit)។ សូមជ្រើស quality ទាបជាង។')
        size_mb = size / (1024 * 1024)
        format_name = 'MP3 Audio' if kind == 'mp3' else f'MP4 {quality}p'
        media_caption = f'✅ Download successful\n📦 {format_name} • {size_mb:.1f} MB'
        with open(path, 'rb') as f:
            if kind == 'mp3':
                await q.message.reply_audio(f, caption=media_caption)
            else:
                await q.message.reply_video(f, caption=media_caption, supports_streaming=True)
        await status.edit_text(f'✅ ទាញយកបានជោគជ័យ!\nDownload completed successfully.\n\n📦 Format: {format_name}\n💾 Size: {size_mb:.1f} MB\n🎉 File បានផ្ញើរួចរាល់។')
    except Exception:
        logger.exception('Download failed: kind=%s quality=%s url=%s', kind, quality, url)
        await status.edit_text('❌ Download/convert failed. សូមសាក quality ផ្សេង ឬ link ផ្សេង។')
    finally:
        if outdir:
            shutil.rmtree(outdir, ignore_errors=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        logger.warning('Temporary Telegram getUpdates conflict during deploy; retrying.')
        return
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning('Temporary Telegram network error: %s', err)
        return
    logger.exception('Unhandled Telegram error', exc_info=err)


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand('start', 'Start bot / ចាប់ផ្តើម'),
        BotCommand('menu', 'Show main menu / ម៉ឺនុយ'),
        BotCommand('help', 'Help / ជំនួយ'),
    ])


def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('menu', menu_cmd))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CallbackQueryHandler(dl_cb, pattern=r'^dl:'))
    app.add_handler(CallbackQueryHandler(menu_cb, pattern=r'^menu:'))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)
    return app
