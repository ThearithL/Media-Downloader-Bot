# MediaMate Telegram Bot + Mini App

For public media you own or are authorized to download. Does not bypass DRM/private access or platform protections.

## Render
1. Push this folder to GitHub.
2. Create a Render Web Service (or Blueprint using render.yaml).
3. Add BOT_TOKEN, WEB_APP_URL, WEBHOOK_SECRET, ADMIN_USER_IDS.
4. Deploy. Open /health to verify {"ok":true}.
5. In BotFather configure the Mini App URL to WEB_APP_URL.

## FFmpeg
MP3 extraction and merged MP4 formats require ffmpeg. If your Render runtime does not expose ffmpeg, add an ffmpeg installation step or use a Docker deployment.

## Free hosting note
Render Free may spin down when idle. Telegram webhook requests can wake it, but the first request after idle can be delayed. Do not rely on self-pinging loops. An external uptime monitor can call /health if its terms and Render's current free-tier terms allow it, but this is not a guarantee of permanent 24/7 uptime.

## Local
cp .env.example .env
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:10000
"# Media-Downloader-Bot" 
