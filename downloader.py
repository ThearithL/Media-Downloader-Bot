import os
import tempfile
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# Public/authorized media only. No DRM/private-access bypass.

BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'socket_timeout': 20,
    'retries': 3,
    'fragment_retries': 3,
    'extractor_retries': 3,
    'geo_bypass': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    },
}


def _is_youtube(url):
    host = (urlparse(url).hostname or '').lower()
    return host == 'youtu.be' or host.endswith('youtube.com') or host.endswith('youtube-nocookie.com')


def _extract(url, download=False, extra=None):
    """Extract metadata/media with safe public-client fallbacks for YouTube."""
    attempts = [{}]
    if _is_youtube(url):
        # YouTube changes player responses frequently. Trying official public
        # client profiles makes extraction more resilient on cloud hosts.
        attempts = [
            {'extractor_args': {'youtube': {'player_client': ['android_vr', 'web_safari']}}},
            {'extractor_args': {'youtube': {'player_client': ['web', 'mweb']}}},
            {},
        ]

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
    formats = []
    seen = set()
    for f in info.get('formats') or []:
        h = f.get('height')
        if h and h not in seen:
            seen.add(h)
            formats.append(h)
    return {
        'title': info.get('title') or 'Media',
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'extractor': info.get('extractor_key') or info.get('extractor'),
        'qualities': sorted(formats, reverse=True)[:8],
    }


def download(url, kind='mp4', quality='720'):
    outdir = tempfile.mkdtemp(prefix='media_')
    tmpl = os.path.join(outdir, '%(title).80s-%(id)s.%(ext)s')
    if kind == 'mp3':
        extra = {
            'format': 'bestaudio/best',
            'outtmpl': tmpl,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        }
    else:
        q = int(quality) if str(quality).isdigit() else 720
        extra = {
            'format': f'bestvideo[height<={q}]+bestaudio/best[height<={q}]/best',
            'merge_output_format': 'mp4',
            'outtmpl': tmpl,
        }

    info, ydl = _extract(url, download=True, extra=extra)
    path = ydl.prepare_filename(info)
    if kind == 'mp3':
        path = os.path.splitext(path)[0] + '.mp3'
    elif not os.path.exists(path):
        mp4 = os.path.splitext(path)[0] + '.mp4'
        if os.path.exists(mp4):
            path = mp4
    return path, outdir
