const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  try { tg.requestFullscreen?.(); } catch (_) {}
}

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const status = $('#status');
const result = $('#result');
let current = null;

const load = (key, fallback) => {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
};
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));

function showView(name) {
  $$('.view').forEach(v => v.classList.add('hidden'));
  const view = name === 'history' ? $('#historyView') : name === 'settings' ? $('#settingsView') : $('#downloadView');
  view.classList.remove('hidden');
  $('#back').classList.toggle('hidden', name === 'download');
  if (name === 'history') renderHistory();
}

function addHistory(item) {
  const history = load('mediamate_history', []);
  const next = [item, ...history.filter(x => x.url !== item.url)].slice(0, 30);
  save('mediamate_history', next);
}

function renderHistory() {
  const history = load('mediamate_history', []);
  $('#historyList').innerHTML = history.length ? history.map((x, i) => `<button class="history-item" data-index="${i}"><strong>${escapeHtml(x.title || 'Media')}</strong><small>${escapeHtml(x.extractor || '')}</small></button>`).join('') : '<p>No history yet.</p>';
  $$('.history-item').forEach(btn => btn.onclick = () => {
    const item = history[Number(btn.dataset.index)];
    $('#url').value = item.url;
    showView('download');
    analyzeUrl();
  });
}

function escapeHtml(value='') {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

async function analyzeUrl() {
  const url = $('#url').value.trim();
  if (!url) { status.textContent = 'សូមបញ្ចូល Link។'; return; }
  status.textContent = '🔍 Analyzing...';
  result.classList.add('hidden');
  $('#analyze').disabled = true;
  try {
    const r = await fetch('/api/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Analyze failed');
    current = {...d, url};
    $('#title').textContent = d.title || 'Media';
    $('#meta').textContent = `${d.extractor || 'Media'} • ${d.duration ? Math.floor(d.duration/60)+':'+String(d.duration%60).padStart(2,'0') : '—'}`;
    $('#thumb').src = d.thumbnail || '';
    $('#thumb').classList.toggle('hidden', !d.thumbnail);
    $('#qualities').innerHTML = (d.qualities || []).map(q => `<button class="quality" data-quality="${q}">${q}p</button>`).join('') || '<span>Best available</span>';
    result.classList.remove('hidden');
    status.textContent = '✅ Link detected';
    addHistory({url, title:d.title, extractor:d.extractor, thumbnail:d.thumbnail, time:Date.now()});
  } catch (e) {
    status.textContent = `❌ ${e.message || 'Unsupported, private, or unavailable link.'}`;
  } finally { $('#analyze').disabled = false; }
}

function sendToBot(kind) {
  const url = current?.url || $('#url').value.trim();
  if (!url) { status.textContent = 'សូម Analyze Link ជាមុនសិន។'; showView('download'); return; }
  const payload = JSON.stringify({action:'download', kind, url});
  if (tg?.sendData) {
    try { tg.sendData(payload); status.textContent = `✅ Sent ${kind.toUpperCase()} request to bot`; return; } catch (_) {}
  }
  navigator.clipboard?.writeText(url);
  status.textContent = 'Link copied. Return to the bot and paste it.';
}

$('#analyze').onclick = analyzeUrl;
$('#url').addEventListener('keydown', e => { if (e.key === 'Enter') analyzeUrl(); });
$('#mp3Action').onclick = () => sendToBot('mp3');
$('#mp4Action').onclick = () => sendToBot('mp4');
$('#favoriteAction').onclick = () => {
  if (!current) return status.textContent = 'Analyze a link first.';
  const fav = load('mediamate_favorites', []);
  save('mediamate_favorites', [current, ...fav.filter(x => x.url !== current.url)].slice(0, 50));
  status.textContent = '⭐ Saved to favorites';
};

$$('nav button').forEach(btn => btn.onclick = () => {
  const tab = btn.dataset.tab;
  if (tab === 'mp3' || tab === 'mp4') { showView('download'); sendToBot(tab); }
  else showView(tab || 'download');
});
$('#back').onclick = () => showView('download');
$('#clearHistory').onclick = () => { save('mediamate_history', []); renderHistory(); };

const settings = load('mediamate_settings', {language:'en', expanded:true, theme:'dark'});
$('#language').value = settings.language;
$('#expanded').checked = settings.expanded;
$('#language').onchange = () => { settings.language = $('#language').value; save('mediamate_settings', settings); };
$('#expanded').onchange = () => { settings.expanded = $('#expanded').checked; save('mediamate_settings', settings); if (settings.expanded) tg?.expand?.(); };

function applyTheme() { document.body.classList.toggle('light', settings.theme === 'light'); }
$('#theme').onclick = () => { settings.theme = settings.theme === 'light' ? 'dark' : 'light'; save('mediamate_settings', settings); applyTheme(); };
applyTheme();
if (settings.expanded) tg?.expand?.();
showView('download');
