import os
import shutil
import tempfile
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# Public/authorized media only. No DRM/private/login bypass.

BASE_OPTS = {
    'quiet': True,
    'no_warnings': False,
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 5,
    'fragment_retries': 5,
    'extractor_retries': 3,
    'file_access_retries': 3,
    'concurrent_fragment_downloads': 4,
    'geo_bypass': True,
    'windowsfilenames': True,
    'trim_file_name': 100,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    },
}


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
        'vimeo.com': 'Vimeo',
        'twitch.tv': 'Twitch',
        'soundcloud.com': 'SoundCloud',
        'pinterest.com': 'Pinterest', 'pin.it': 'Pinterest',
        'threads.net': 'Threads',
    }
    for domain, name in mapping.items():
        if host == domain or host.endswith('.' + domain):
            return name
    return None


def _youtube_attempts():
    return [
        {'extractor_args': {'youtube': {'player_client': ['default', 'web_embedded']}}},
        {'extractor_args': {'youtube': {'player_client': ['web', 'mweb']}}},
        {'extractor_args': {'youtube': {'player_client': ['android']}}},
        {},
    ]


def _extract(url, download=False, extra=None):
    attempts = _youtube_attempts() if _is_youtube(url) else [{}]
    last_error = None
    for attempt in attempts:
        opts = dict(BASE_OPTS)
        opts.update(attempt)
        if extra:
            opts.update(extra)
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download), ydl
        except DownloadError as exc:
            last_error = exc
    raise last_error or DownloadError('Unable to extract media information')


def analyze(url):
    info, _ = _extract(url, download=False, extra={'skip_download': True})
    formats, seen = [], set()
    for f in info.get('formats') or []:
        h = f.get('height')
        if h and h not in seen:
            seen.add(h)
            formats.append(h)
    return {
        'title': info.get('title') or info.get('description') or 'Media',
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'extractor': info.get('extractor_key') or info.get('extractor'),
        'platform': _platform(url) or info.get('extractor_key') or 'Media',
        'uploader': info.get('uploader') or info.get('channel'),
        'qualities': sorted(formats, reverse=True)[:10],
    }


def _find_output(outdir, kind):
    files = [os.path.join(outdir, f) for f in os.listdir(outdir) if os.path.isfile(os.path.join(outdir, f))]
    if not files:
        return None
    if kind == 'mp3':
        mp3s = [f for f in files if f.lower().endswith('.mp3')]
        if mp3s:
            return max(mp3s, key=os.path.getsize)
    media = [f for f in files if not f.lower().endswith(('.part', '.ytdl', '.json'))]
    return max(media or files, key=os.path.getsize)


def download(url, kind='mp4', quality='720'):
    outdir = tempfile.mkdtemp(prefix='media_')
    tmpl = os.path.join(outdir, '%(title).80s-%(id)s.%(ext)s')
    has_ffmpeg = bool(shutil.which('ffmpeg'))

    try:
        if kind == 'mp3':
            if not has_ffmpeg:
                raise RuntimeError('FFmpeg is required for MP3 conversion')
            extra = {
                'format': 'bestaudio/best',
                'outtmpl': tmpl,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            }
        else:
            q = int(quality) if str(quality).isdigit() else 720
            # Prefer a single MP4 file first. This works even on hosts where
            # FFmpeg is unavailable. When FFmpeg exists, yt-dlp can merge the
            # higher quality video/audio streams as a fallback.
            if has_ffmpeg:
                fmt = f'bestvideo[height<={q}]+bestaudio/best[height<={q}]/best'
            else:
                fmt = f'best[ext=mp4][height<={q}]/best[height<={q}]/best'
            extra = {'format': fmt, 'outtmpl': tmpl}
            if has_ffmpeg:
                extra['merge_output_format'] = 'mp4'

        info, ydl = _extract(url, download=True, extra=extra)
        path = ydl.prepare_filename(info)
        if kind == 'mp3':
            path = os.path.splitext(path)[0] + '.mp3'
        elif not os.path.exists(path):
            mp4 = os.path.splitext(path)[0] + '.mp4'
            if os.path.exists(mp4):
                path = mp4

        if not os.path.exists(path):
            path = _find_output(outdir, kind)
        if not path or not os.path.exists(path):
            raise RuntimeError('Downloaded media file was not created')
        return path, outdir
    except Exception:
        shutil.rmtree(outdir, ignore_errors=True)
        raise
