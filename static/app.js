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
let selectedQuality = '720';

const load = (key, fallback) => {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
};
const save = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {} };

function showView(name) {
  $$('.view').forEach(v => v.classList.add('hidden'));
  const map = {history: $('#historyView'), favorites: $('#favoritesView'), settings: $('#settingsView')};
  (map[name] || $('#downloadView')).classList.remove('hidden');
  $('#back').classList.toggle('hidden', name === 'download');
  if (name === 'history') renderHistory();
  if (name === 'favorites') renderFavorites();
}

function addHistory(item) {
  const history = load('mediamate_history', []);
  save('mediamate_history', [item, ...history.filter(x => x.url !== item.url)].slice(0, 30));
}

function escapeHtml(value='') {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

function renderSaved(list, target, emptyText) {
  target.innerHTML = list.length ? list.map((x, i) => `<button class="history-item" data-index="${i}"><strong>${escapeHtml(x.title || 'Media')}</strong><small>${escapeHtml(x.extractor || x.platform || '')}</small></button>`).join('') : `<p>${emptyText}</p>`;
  target.querySelectorAll('.history-item').forEach(btn => btn.addEventListener('click', () => {
    const item = list[Number(btn.dataset.index)];
    $('#url').value = item.url;
    showView('download');
    analyzeUrl();
  }));
}

function renderHistory() { renderSaved(load('mediamate_history', []), $('#historyList'), 'No history yet.'); }
function renderFavorites() { renderSaved(load('mediamate_favorites', []), $('#favoritesList'), 'No favorites yet.'); }

function selectQuality(q) {
  selectedQuality = String(q || '720');
  $$('.quality').forEach(btn => btn.classList.toggle('selected', btn.dataset.quality === selectedQuality));
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
    $('#meta').textContent = `${d.platform || d.extractor || 'Media'} • ${d.duration ? Math.floor(d.duration/60)+':'+String(d.duration%60).padStart(2,'0') : '—'}`;
    $('#thumb').src = d.thumbnail || '';
    $('#thumb').classList.toggle('hidden', !d.thumbnail);
    const qualities = d.qualities || [];
    $('#qualities').innerHTML = qualities.map(q => `<button type="button" class="quality" data-quality="${q}">${q}p</button>`).join('') || '<span>Best available</span>';
    selectedQuality = String(qualities[0] || 720);
    $$('.quality').forEach(btn => btn.addEventListener('click', () => selectQuality(btn.dataset.quality)));
    selectQuality(selectedQuality);
    result.classList.remove('hidden');
    status.textContent = '✅ Link detected';
    addHistory({url, title:d.title, extractor:d.extractor, platform:d.platform, thumbnail:d.thumbnail, time:Date.now()});
  } catch (e) {
    status.textContent = `❌ ${e.message || 'Unsupported, private, or unavailable link.'}`;
  } finally { $('#analyze').disabled = false; }
}

function sendToBot(kind) {
  const url = current?.url || $('#url').value.trim();
  if (!url) { status.textContent = 'សូម Analyze Link ជាមុនសិន។'; showView('download'); return; }
  if (!current) { status.textContent = 'សូម Analyze Link ជាមុនសិន។'; showView('download'); return; }
  const payload = JSON.stringify({action:'download', kind, quality: kind === 'mp3' ? '192' : selectedQuality, url});
  if (tg?.sendData) {
    try {
      tg.sendData(payload);
      status.textContent = `✅ Sent ${kind.toUpperCase()} request to bot`;
      return;
    } catch (e) {
      status.textContent = '❌ Telegram could not receive this request. Open Mini App from the bot keyboard.';
      return;
    }
  }
  status.textContent = '❌ Open this Mini App from the Telegram bot keyboard to download.';
}

$('#analyze').addEventListener('click', analyzeUrl);
$('#url').addEventListener('keydown', e => { if (e.key === 'Enter') analyzeUrl(); });
$('#mp3Action').addEventListener('click', () => sendToBot('mp3'));
$('#mp4Action').addEventListener('click', () => sendToBot('mp4'));
$('#favoriteAction').addEventListener('click', () => {
  if (!current) { status.textContent = 'Analyze a link first.'; return; }
  const fav = load('mediamate_favorites', []);
  save('mediamate_favorites', [current, ...fav.filter(x => x.url !== current.url)].slice(0, 50));
  status.textContent = '⭐ Saved to favorites';
});

$$('nav button').forEach(btn => btn.addEventListener('click', () => {
  const tab = btn.dataset.tab || 'download';
  if (tab === 'mp3' || tab === 'mp4') { showView('download'); if (current) sendToBot(tab); else status.textContent = `Paste and Analyze a link, then choose ${tab.toUpperCase()}.`; }
  else showView(tab);
}));
$('#back').addEventListener('click', () => showView('download'));
$('#clearHistory').addEventListener('click', () => { save('mediamate_history', []); renderHistory(); });
$('#clearFavorites').addEventListener('click', () => { save('mediamate_favorites', []); renderFavorites(); });

const settings = load('mediamate_settings', {language:'en', expanded:true, theme:'dark'});
$('#language').value = settings.language;
$('#expanded').checked = settings.expanded;
$('#language').addEventListener('change', () => { settings.language = $('#language').value; save('mediamate_settings', settings); status.textContent = settings.language === 'km' ? '✅ បានរក្សាទុកភាសាខ្មែរ' : '✅ English saved'; });
$('#expanded').addEventListener('change', () => { settings.expanded = $('#expanded').checked; save('mediamate_settings', settings); if (settings.expanded) tg?.expand?.(); });

function applyTheme() { document.body.classList.toggle('light', settings.theme === 'light'); }
$('#theme').addEventListener('click', () => { settings.theme = settings.theme === 'light' ? 'dark' : 'light'; save('mediamate_settings', settings); applyTheme(); });
applyTheme();
if (settings.expanded) tg?.expand?.();
showView('download');
