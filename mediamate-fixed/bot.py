import asyncio, os, shutil, threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import BOT_TOKEN, WEB_APP_URL
from downloader import analyze, download

MENU=[['📥 Download','🎵 MP3'],['🎬 MP4','🖼️ Image'],['📜 History','⭐ Favorites'],['📊 Statistics','🌐 Language'],['⚙️ Settings','❓ Help']]

def home_keyboard():
    rows=[]
    for row in MENU:
        rows.append([InlineKeyboardButton(x, callback_data='menu:'+x) for x in row])
    if WEB_APP_URL: rows.append([InlineKeyboardButton('📱 Open Mini App', web_app=WebAppInfo(WEB_APP_URL))])
    return InlineKeyboardMarkup(rows)

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('សួស្តី 👋\nផ្ញើ public media link ដែលអ្នកមានសិទ្ធិទាញយក ឬបើក Mini App។\n\nSend an authorized public media link to analyze it.', reply_markup=home_keyboard())

async def help_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('🔗 Paste a supported public URL. I will show metadata and available quality.\n🎬 MP4 / 🎵 MP3 are available when the source permits extraction.\n🔒 Private/DRM-protected content is not bypassed.')

async def menu_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); name=q.data.split(':',1)[1]
    texts={'📥 Download':'ផ្ញើ Link មកខ្ញុំ ដើម្បី Analyze និង Download។','🎵 MP3':'ផ្ញើ Link ហើយជ្រើស 🎵 MP3។','🎬 MP4':'ផ្ញើ Link ហើយជ្រើស quality។','🖼️ Image':'Thumbnail នឹងបង្ហាញបើ source មាន។','📜 History':'V1: History database module នឹងបន្ថែមបន្ទាប់។','⭐ Favorites':'V1: Favorites database module នឹងបន្ថែមបន្ទាប់។','📊 Statistics':'V1: Statistics នឹងបន្ថែមបន្ទាប់។','🌐 Language':'V1 supports Khmer + English UI text.','⚙️ Settings':'Settings are available in Mini App.','❓ Help':'ផ្ញើ /help សម្រាប់ជំនួយ។'}
    await q.message.reply_text(texts.get(name,name))

async def link_handler(update:Update, context:ContextTypes.DEFAULT_TYPE):
    url=(update.effective_message.text or '').strip()
    if not (url.startswith('http://') or url.startswith('https://')): return
    msg=await update.effective_message.reply_text('🔍 កំពុងពិនិត្យ Link...')
    try:
        data=await asyncio.to_thread(analyze,url); context.user_data['url']=url
        qs=data['qualities'][:5] or [720,480,360]
        rows=[[InlineKeyboardButton(f'🎬 {q}p',callback_data=f'dl:mp4:{q}') for q in qs[:3]]]
        if len(qs)>3: rows.append([InlineKeyboardButton(f'🎬 {q}p',callback_data=f'dl:mp4:{q}') for q in qs[3:]])
        rows.append([InlineKeyboardButton('🎵 MP3',callback_data='dl:mp3:192')])
        dur=data['duration']; duration=f'{dur//60}:{dur%60:02d}' if isinstance(dur,int) else '—'
        text=f"✅ Link Detected\n\n🎬 {data['title']}\n🌐 {data['extractor']}\n⏱ {duration}\n\nជ្រើស format / quality:"
        await msg.edit_text(text,reply_markup=InlineKeyboardMarkup(rows))
        if data.get('thumbnail'): await update.effective_message.reply_photo(data['thumbnail'])
    except Exception as e:
        await msg.edit_text('❌ មិនអាច Analyze Link នេះបានទេ។ Link អាច private, unsupported ឬ source បានផ្លាស់ប្តូរ។')

async def dl_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); url=context.user_data.get('url')
    if not url: return await q.message.reply_text('សូមផ្ញើ Link ម្តងទៀត។')
    _,kind,quality=q.data.split(':'); status=await q.message.reply_text('⚙️ Processing...')
    outdir=None
    try:
        path,outdir=await asyncio.to_thread(download,url,kind,quality)
        size=os.path.getsize(path)
        if size>49*1024*1024:
            await status.edit_text('⚠️ File ធំពេកសម្រាប់ V1 Telegram upload limit ដែល project នេះកំណត់ (49 MB)។ សូមជ្រើស quality ទាបជាង។'); return
        with open(path,'rb') as f:
            if kind=='mp3': await q.message.reply_audio(f,caption='✅ Done')
            else: await q.message.reply_video(f,caption='✅ Done',supports_streaming=True)
        await status.delete()
    except Exception:
        await status.edit_text('❌ Download/convert failed. សូមសាក quality ផ្សេង ឬ link ផ្សេង។')
    finally:
        if outdir: shutil.rmtree(outdir,ignore_errors=True)

def build_app():
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('help',help_cmd))
    app.add_handler(CallbackQueryHandler(dl_cb,pattern=r'^dl:')); app.add_handler(CallbackQueryHandler(menu_cb,pattern=r'^menu:'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,link_handler)); return app
