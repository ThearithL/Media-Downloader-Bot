import os, tempfile
from yt_dlp import YoutubeDL

# Public/authorized media only. No DRM/private-access bypass.
def analyze(url):
    opts={'quiet':True,'no_warnings':True,'skip_download':True,'noplaylist':True}
    with YoutubeDL(opts) as ydl:
        info=ydl.extract_info(url, download=False)
    formats=[]
    seen=set()
    for f in info.get('formats') or []:
        h=f.get('height')
        if h and h not in seen:
            seen.add(h); formats.append(h)
    return {
        'title': info.get('title') or 'Media', 'thumbnail':info.get('thumbnail'),
        'duration':info.get('duration'), 'extractor':info.get('extractor_key') or info.get('extractor'),
        'qualities':sorted(formats, reverse=True)[:8]
    }

def download(url, kind='mp4', quality='720'):
    outdir=tempfile.mkdtemp(prefix='media_')
    tmpl=os.path.join(outdir,'%(title).80s-%(id)s.%(ext)s')
    if kind=='mp3':
        opts={'format':'bestaudio/best','outtmpl':tmpl,'noplaylist':True,'quiet':True,
              'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}]}
    else:
        q=int(quality) if str(quality).isdigit() else 720
        opts={'format':f'bestvideo[height<={q}]+bestaudio/best[height<={q}]/best','merge_output_format':'mp4',
              'outtmpl':tmpl,'noplaylist':True,'quiet':True}
    with YoutubeDL(opts) as ydl:
        info=ydl.extract_info(url, download=True)
        path=ydl.prepare_filename(info)
    if kind=='mp3': path=os.path.splitext(path)[0]+'.mp3'
    elif not os.path.exists(path):
        base=os.path.splitext(path)[0]+'.mp4'
        if os.path.exists(base): path=base
    return path, outdir
