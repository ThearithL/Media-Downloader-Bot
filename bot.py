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
    await update.effective_message.reply_text('សួស្តី 👋\nផ្ញើ public media link ដែលអ្នកមានសិទ្ធិទាញយក ឬជ្រើស Menu ខាងក្រោម។\n\nSend an authorized public media link or choose a menu.', reply_markup=persistent_menu())
    await update.effective_message.reply_text('⚡ Quick actions', reply_markup=home_keyboard())


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('📋 Main Menu / ម៉ឺនុយមេ', reply_markup=persistent_menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('🔗 Paste a supported public media URL.\n🎬 MP4 / 🎵 MP3 are available when the source permits extraction.\n📎 Uploaded video/image/file receives an immediate acknowledgement.\n🔒 Private/DRM-protected content is not bypassed.', reply_markup=persistent_menu())


async def handle_menu_name(message, name):
    texts = {'📥 Download':'📥 ផ្ញើ public media Link មកខ្ញុំ។','🎵 MP3':'🎵 ផ្ញើ Link មកខ្ញុំ បន្ទាប់មកជ្រើស MP3។','🎬 MP4':'🎬 ផ្ញើ Link មកខ្ញុំ ហើយជ្រើស video quality។','🖼️ Image':'🖼️ ផ្ញើរូបភាពមក Bot បានដោយផ្ទាល់។','📜 History':'📜 History មាននៅក្នុង Mini App។','⭐ Favorites':'⭐ Favorites មាននៅក្នុង Mini App។','📊 Statistics':'📊 Statistics នឹងបន្ថែមនៅ version បន្ទាប់។','🌐 Language':'🌐 Mini App supports Khmer + English settings.','⚙️ Settings':'⚙️ Settings មាននៅក្នុង Mini App។','❓ Help':'❓ ផ្ញើ /help សម្រាប់ជំនួយ។'}
    await message.reply_text(texts.get(name, name), reply_markup=persistent_menu())


async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await handle_menu_name(q.message, q.data.split(':', 1)[1])


def friendly_extract_error(exc):
    detail = str(exc).lower()
    if '404' in detail or 'not found' in detail:
        return '🔗 Link នេះមិនមានទៀត ឬ destination បានត្រឡប់ 404 Not Found។ សូមពិនិត្យ Link ហើយផ្ញើ public media link ថ្មី។'
    if '429' in detail or 'too many requests' in detail:
        return '⏳ YouTube/Source កំពុង rate-limit server (429)។ សូមរង់ចាំបន្តិច ហើយសាកម្តងទៀត។'
    if '403' in detail or 'forbidden' in detail:
        return '🚫 YouTube/Source បានបដិសេធ request ពី server (403)។ សូមសាកពេលក្រោយ ឬ source ផ្សេង។'
    if 'sign in' in detail or 'cookies' in detail or 'login' in detail:
        return '🔐 Media នេះត្រូវការ authorized login/cookies។ Bot មិន bypass private/restricted media ទេ។'
    if 'javascript runtime' in detail or 'deno' in detail or 'ejs' in detail:
        return '⚙️ Server ខ្វះ JavaScript runtime សម្រាប់ YouTube extraction។ ត្រូវ deploy ជា Docker ដែលមាន Deno។'
    if 'player response' in detail:
        return '❌ YouTube extraction មិនបានទទួល player response។ yt-dlp/runtime ឬ YouTube server access ត្រូវបានរារាំង។'
    if 'unsupported url' in detail or 'unsupported' in detail:
        return '❌ Link នេះមិនមែនជា supported media link ទេ។ សូមផ្ញើ YouTube, TikTok, Facebook, Instagram ឬ public media link ដែល bot អាច extract បាន។'
    return '❌ មិនអាច Analyze Link នេះបានទេ។ Source អាចមិនមែនជា media, private, expired ឬ unavailable។'


async def analyze_and_reply(message, context, url, status=None):
    msg = status or await message.reply_text('⚡ Received • កំពុងពិនិត្យ Link...')
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
        logger.warning('Analyze failed for URL %s: %s', url, exc)
        await msg.edit_text(friendly_extract_error(exc))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or '').strip()
    if text in {item for row in MENU for item in row}:
        return await handle_menu_name(update.effective_message, text)
    if text.startswith(('http://', 'https://')):
        status = await update.effective_message.reply_text('⚡ Received • Processing link...')
        return await analyze_and_reply(update.effective_message, context, text, status=status)
    await update.effective_message.reply_text('🔗 សូមផ្ញើ public media link ឬជ្រើស Menu ខាងក្រោម។', reply_markup=persistent_menu())


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message.video: media, kind = message.video, 'Video'
    elif message.photo: media, kind = message.photo[-1], 'Image'
    elif message.animation: media, kind = message.animation, 'Animation'
    elif message.audio: media, kind = message.audio, 'Audio'
    elif message.document: media, kind = message.document, 'File'
    else: return
    size = getattr(media, 'file_size', None)
    size_text = f' • {size / (1024 * 1024):.1f} MB' if size else ''
    await message.reply_text(f'⚡ Received {kind}{size_text}\n✅ Bot បានទទួល file របស់អ្នកភ្លាមៗ។\n\nសម្រាប់ download/convert ពី social media សូមផ្ញើ public media link។', reply_markup=persistent_menu())


async def webapp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    raw = message.web_app_data.data if message and message.web_app_data else ''
    try: data = json.loads(raw)
    except Exception: return await message.reply_text('❌ Invalid Mini App request.')
    url = str(data.get('url', '')).strip()
    if not url.startswith(('http://', 'https://')): return await message.reply_text('❌ Invalid URL from Mini App.')
    context.user_data['url'] = url
    status = await message.reply_text('⚡ Received • Processing Mini App link...')
    await analyze_and_reply(message, context, url, status=status)


async def dl_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    url = context.user_data.get('url')
    if not url: return await q.message.reply_text('សូមផ្ញើ Link ម្តងទៀត។')
    _, kind, quality = q.data.split(':')
    status = await q.message.reply_text('⚡ Download request received • Processing...')
    outdir = None
    try:
        path, outdir = await asyncio.to_thread(download, url, kind, quality)
        if not os.path.exists(path): raise FileNotFoundError(path)
        size = os.path.getsize(path)
        if size > 49 * 1024 * 1024: return await status.edit_text('⚠️ File ធំពេក (49 MB limit)។ សូមជ្រើស quality ទាបជាង។')
        size_mb = size / (1024 * 1024)
        format_name = 'MP3 Audio' if kind == 'mp3' else f'MP4 {quality}p'
        with open(path, 'rb') as f:
            if kind == 'mp3': await q.message.reply_audio(f, caption=f'✅ Download successful\n📦 {format_name} • {size_mb:.1f} MB')
            else: await q.message.reply_video(f, caption=f'✅ Download successful\n📦 {format_name} • {size_mb:.1f} MB', supports_streaming=True)
        await status.edit_text(f'✅ ទាញយកបានជោគជ័យ!\nDownload completed successfully.\n\n📦 Format: {format_name}\n💾 Size: {size_mb:.1f} MB')
    except Exception as exc:
        logger.warning('Download failed: kind=%s quality=%s url=%s error=%s', kind, quality, url, exc)
        await status.edit_text(friendly_extract_error(exc))
    finally:
        if outdir: shutil.rmtree(outdir, ignore_errors=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict): logger.warning('Temporary Telegram getUpdates conflict during deploy; retrying.'); return
    if isinstance(err, (TimedOut, NetworkError)): logger.warning('Temporary Telegram network error: %s', err); return
    logger.exception('Unhandled Telegram error', exc_info=err)


async def post_init(application):
    await application.bot.set_my_commands([BotCommand('start', 'Start bot / ចាប់ផ្តើម'), BotCommand('menu', 'Show main menu / ម៉ឺនុយ'), BotCommand('help', 'Help / ជំនួយ')])


def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start', start)); app.add_handler(CommandHandler('menu', menu_cmd)); app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CallbackQueryHandler(dl_cb, pattern=r'^dl:')); app.add_handler(CallbackQueryHandler(menu_cb, pattern=r'^menu:'))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO | filters.ANIMATION | filters.AUDIO | filters.Document.ALL, media_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)); app.add_error_handler(error_handler)
    return app
