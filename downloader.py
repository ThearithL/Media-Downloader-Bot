import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from urllib.parse import urlparse

import yt_dlp
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# Public/authorized media only. No DRM/private/login bypass.
logger = logging.getLogger('mediamate.downloader')

BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    # Keep Telegram interactions responsive on slow/blocked hosting egress.
    'socket_timeout': 7,
    'retries': 0,
    'fragment_retries': 0,
    'extractor_retries': 0,
    'file_access_retries': 0,
    'concurrent_fragment_downloads': 8,
    'buffersize': 1024 * 1024,
    'http_chunk_size': 10 * 1024 * 1024,
    'windowsfilenames': True,
    'trim_file_name': 80,
    'js_runtimes': {'deno': {}},
}

_DIAGNOSTICS_LOGGED = False


def _host(url):
    return (urlparse(url).hostname or '').lower().removeprefix('www.')


def _is_youtube(url):
    host = _host(url)
    return host == 'youtu.be' or host.endswith('youtube.com') or host.endswith('youtube-nocookie.com')


def _platform(url):
    host = _host(url)
    mapping = {
        'youtube.com': 'YouTube', 'youtu.be': 'YouTube',
        'tiktok.com': 'TikTok', 'vm.tiktok.com': 'TikTok',
        'facebook.com': 'Facebook', 'fb.watch': 'Facebook',
        'instagram.com': 'Instagram',
        'twitter.com': 'X / Twitter', 'x.com': 'X / Twitter',
        'reddit.com': 'Reddit', 'redd.it': 'Reddit',
        'vimeo.com': 'Vimeo', 'twitch.tv': 'Twitch',
        'soundcloud.com': 'SoundCloud',
        'pinterest.com': 'Pinterest', 'pin.it': 'Pinterest',
        'threads.net': 'Threads',
    }
    for domain, name in mapping.items():
        if host == domain or host.endswith('.' + domain):
            return name
    return None


def _safe_version(command):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        line = (proc.stdout or proc.stderr or '').strip().splitlines()
        return line[0][:160] if line else 'unknown'
    except Exception as exc:
        return f'unavailable ({type(exc).__name__})'


def _log_youtube_diagnostics_once():
    global _DIAGNOSTICS_LOGGED
    if _DIAGNOSTICS_LOGGED:
        return
    _DIAGNOSTICS_LOGGED = True
    server_home = os.getenv('BGUTIL_SERVER_HOME', '/opt/bgutil-ytdlp-pot-provider/server')
    base_url = os.getenv('BGUTIL_BASE_URL', 'http://127.0.0.1:4416')
    logger.warning(
        'YouTube diagnostics: yt-dlp=%s deno=%s deno_path=%s ffmpeg_path=%s bgutil_server_home=%s bgutil_server_exists=%s bgutil_base_url=%s',
        getattr(getattr(yt_dlp, 'version', None), '__version__', 'unknown'),
        _safe_version(['deno', '--version']),
        shutil.which('deno'),
        shutil.which('ffmpeg'),
        server_home,
        os.path.isdir(server_home),
        base_url,
    )


def _youtube_attempts():
    base_url = os.getenv('BGUTIL_BASE_URL', 'http://127.0.0.1:4416')
    return [
        ('mweb+bgutil-http', {'extractor_args': {
            'youtube': {'player_client': ['mweb']},
            'youtubepot-bgutilhttp': {'base_url': [base_url]},
        }}),
        ('web_embedded', {'extractor_args': {'youtube': {'player_client': ['web_embedded']}}}),
    ]


def _looks_like_server_block(exc):
    detail = str(exc).lower()
    return any(marker in detail for marker in (
        'failed to extract any player response',
        '429', 'too many requests', '403', 'forbidden',
        'ip is likely being blocked', 'confirm you’re not a bot', "confirm you're not a bot",
    ))


def _should_stop_youtube_retry(exc):
    detail = str(exc).lower()
    return any(marker in detail for marker in (
        'failed to extract any player response',
        '429', 'too many requests', '403', 'forbidden',
        'sign in', 'login required', 'private video', 'members-only',
        'ip is likely being blocked', 'confirm you’re not a bot', "confirm you're not a bot",
    ))


def _extract(url, download=False, extra=None):
    youtube = _is_youtube(url)
    if youtube:
        _log_youtube_diagnostics_once()
    attempts = _youtube_attempts() if youtube else [('default', {})]
    last_error = None
    server_block_count = 0

    for label, attempt in attempts:
        opts = dict(BASE_OPTS)
        opts.update(attempt)
        if extra:
            opts.update(extra)
        if youtube:
            logger.warning('YouTube extraction attempt=%s video_host=%s download=%s', label, _host(url), download)
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
                filename = ydl.prepare_filename(info) if download else None
                if youtube:
                    logger.warning('YouTube extraction success attempt=%s extractor=%s formats=%s', label, info.get('extractor'), len(info.get('formats') or []))
                return info, filename
        except DownloadError as exc:
            last_error = exc
            if youtube:
                logger.warning('YouTube extraction failed attempt=%s error=%s', label, str(exc)[:700])
                if _looks_like_server_block(exc):
                    server_block_count += 1
            if youtube and _should_stop_youtube_retry(exc):
                logger.warning('YouTube retries stopped early for fast response because the source reported a player/access/IP/auth restriction')
                break

    if youtube and server_block_count:
        raise DownloadError(
            'YouTube rejected player responses from this server network. '
            'The runtime and PO-token provider are installed, but this hosting egress cannot currently obtain a usable player response.'
        )
    raise last_error or DownloadError('Unable to extract media information')


def analyze(url):
    info, _ = _extract(url, download=False, extra={'skip_download': True})
    heights = {f.get('height') for f in (info.get('formats') or []) if f.get('height')}
    return {
        'title': info.get('title') or info.get('description') or 'Media',
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'extractor': info.get('extractor_key') or info.get('extractor'),
        'platform': _platform(url) or info.get('extractor_key') or 'Media',
        'uploader': info.get('uploader') or info.get('channel'),
        'qualities': sorted(heights, reverse=True)[:8],
    }


def _find_output(outdir, kind):
    files = [os.path.join(outdir, f) for f in os.listdir(outdir) if os.path.isfile(os.path.join(outdir, f))]
    if kind == 'mp3':
        mp3s = [f for f in files if f.lower().endswith('.mp3')]
        if mp3s:
            return max(mp3s, key=os.path.getsize)
    media = [f for f in files if not f.lower().endswith(('.part', '.ytdl', '.json'))]
    return max(media or files, key=os.path.getsize) if files else None


def _telegram_safe_filename(path, kind):
    """Rename media to a short ASCII filename before Telegram upload.

    Telegram clients can display Khmer in captions/messages, but Unicode media
    filenames may render as boxes/garbled glyphs on some client/platform
    combinations. Keep the real Khmer title in the caption and use a portable
    filename for the uploaded file itself.
    """
    if not path or not os.path.exists(path):
        return path
    ext = '.mp3' if kind == 'mp3' else (os.path.splitext(path)[1].lower() or '.mp4')
    stem = os.path.splitext(os.path.basename(path))[0]
    ascii_stem = unicodedata.normalize('NFKD', stem).encode('ascii', 'ignore').decode('ascii')
    ascii_stem = re.sub(r'[^A-Za-z0-9._-]+', '-', ascii_stem).strip('-._')[:48]
    if not ascii_stem:
        ascii_stem = 'media'
    safe_path = os.path.join(os.path.dirname(path), ascii_stem + ext)
    if os.path.abspath(safe_path) != os.path.abspath(path):
        # Avoid accidental collision when yt-dlp generated multiple files.
        if os.path.exists(safe_path):
            safe_path = os.path.join(os.path.dirname(path), f'{ascii_stem}-download{ext}')
        os.replace(path, safe_path)
    return safe_path


def download(url, kind='mp4', quality='720'):
    outdir = tempfile.mkdtemp(prefix='media_')
    # Keep source titles available to yt-dlp while downloading; sanitize only
    # the final upload filename so Khmer metadata/captions are not destroyed.
    tmpl = os.path.join(outdir, '%(title).60s-%(id)s.%(ext)s')
    has_ffmpeg = bool(shutil.which('ffmpeg'))
    try:
        if kind == 'mp3':
            if not has_ffmpeg:
                raise RuntimeError('FFmpeg is required for MP3 conversion')
            extra = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': tmpl,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            }
        else:
            q = int(quality) if str(quality).isdigit() else 720
            if has_ffmpeg:
                fmt = f'best[ext=mp4][height<={q}]/best[height<={q}]/bestvideo[height<={q}]+bestaudio/best'
            else:
                fmt = f'best[ext=mp4][height<={q}]/best[height<={q}]/best'
            extra = {'format': fmt, 'outtmpl': tmpl}
            if has_ffmpeg:
                extra['merge_output_format'] = 'mp4'
        info, path = _extract(url, download=True, extra=extra)
        if kind == 'mp3':
            path = os.path.splitext(path)[0] + '.mp3'
        elif not path or not os.path.exists(path):
            candidate = os.path.splitext(path or '')[0] + '.mp4'
            if candidate and os.path.exists(candidate):
                path = candidate
        if not path or not os.path.exists(path):
            path = _find_output(outdir, kind)
        if not path or not os.path.exists(path):
            raise RuntimeError('Downloaded media file was not created')
        path = _telegram_safe_filename(path, kind)
        return path, outdir
    except Exception:
        shutil.rmtree(outdir, ignore_errors=True)
        raise
