'use strict';

const { filterItems, isPinned, pinKey, move } = window.appbrowser;

const SECTIONS = [
  { key: 'pinned', label: 'Pinned', help: 'Your hand-picked shortcuts' },
  { key: 'recent', label: 'Recent', help: 'Most recently launched' },
  { key: 'frequent', label: 'Frequent', help: 'Most often launched' },
];
const TYPE_OPTIONS = [
  { value: 'all', label: 'All types' },
  { value: 'app', label: 'Apps' },
  { value: 'folder', label: 'Folders' },
  { value: 'site', label: 'Sites' },
];
const APP_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'app', label: 'Apps' },
  { value: 'folder', label: 'Folders' },
  { value: 'site', label: 'Sites' },
];

let config = null;
let allItems = [];
const keyIcon = new Map();        // "type:target" -> icon data URL
const appsState = { type: 'all', query: '' };

const $ = (id) => document.getElementById(id);
const sectionRowsEl = $('section-rows');
const pinnedListEl = $('pinned-list');
const pinnedEmptyEl = $('pinned-empty');
const appsListEl = $('apps-list');
const appsSearchEl = $('apps-search');
const appsFilterEl = $('apps-filter');
const appsCountEl = $('apps-count');
const saveBtn = $('save-btn');
const saveStatus = $('save-status');

// ---------- shared bits ----------
function iconEl(iconUrl, type) {
  if (iconUrl) {
    const img = document.createElement('img');
    img.className = 'row-icon';
    img.src = iconUrl;
    return img;
  }
  const badge = document.createElement('span');
  badge.className = `row-badge ${type || 'app'}`;
  badge.textContent = (type || 'app')[0].toUpperCase();
  return badge;
}

// ---------- tabs ----------
function activateTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) => { p.hidden = p.dataset.panel !== name; });
  if (name === 'apps') appsSearchEl.focus();
}
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => activateTab(t.dataset.tab)));

// ---------- HOME: sections ----------
function renderSections() {
  sectionRowsEl.replaceChildren(...SECTIONS.map(({ key: k, label, help }) => {
    const cfg = config.sections[k];
    const row = document.createElement('div');
    row.className = 'section-row';

    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.className = 'section-toggle';
    enabled.checked = cfg.enabled;
    enabled.addEventListener('change', () => { cfg.enabled = enabled.checked; row.classList.toggle('off', !enabled.checked); });

    const name = document.createElement('div');
    name.className = 'section-name';
    name.innerHTML = `<span class="section-title">${label}</span><span class="section-help">${help}</span>`;

    const type = document.createElement('select');
    TYPE_OPTIONS.forEach((o) => {
      const opt = document.createElement('option');
      opt.value = o.value; opt.textContent = o.label;
      if (o.value === cfg.typeFilter) opt.selected = true;
      type.append(opt);
    });
    type.addEventListener('change', () => { cfg.typeFilter = type.value; });

    const limit = document.createElement('input');
    limit.type = 'number'; limit.min = '0'; limit.value = cfg.limit;
    limit.className = 'limit-input';
    limit.addEventListener('change', () => {
      const n = parseInt(limit.value, 10);
      cfg.limit = Number.isInteger(n) && n >= 0 ? n : cfg.limit;
      limit.value = cfg.limit;
    });

    row.classList.toggle('off', !cfg.enabled);
    row.append(enabled, name, type, limit);
    return row;
  }));
}

// ---------- PINNED ----------
let dragFrom = null;
function renderPinned() {
  pinnedEmptyEl.hidden = config.pinned.length > 0;
  pinnedListEl.replaceChildren(...config.pinned.map((entry, i) => {
    const li = document.createElement('li');
    li.className = 'pinned-row';
    li.draggable = true;

    const handle = document.createElement('span');
    handle.className = 'drag-handle'; handle.textContent = '⠿'; handle.title = 'Drag to reorder';

    const icon = iconEl(keyIcon.get(pinKey(entry)), entry.type);

    const title = document.createElement('span');
    title.className = 'row-title'; title.textContent = entry.title;

    const up = document.createElement('button');
    up.className = 'icon-btn'; up.textContent = '↑'; up.title = 'Move up'; up.disabled = i === 0;
    up.addEventListener('click', () => { config.pinned = move(config.pinned, i, i - 1); renderPinned(); });

    const down = document.createElement('button');
    down.className = 'icon-btn'; down.textContent = '↓'; down.title = 'Move down'; down.disabled = i === config.pinned.length - 1;
    down.addEventListener('click', () => { config.pinned = move(config.pinned, i, i + 1); renderPinned(); });

    const remove = document.createElement('button');
    remove.className = 'icon-btn danger'; remove.textContent = '✕'; remove.title = 'Unpin';
    remove.addEventListener('click', () => { config.pinned.splice(i, 1); renderPinned(); });

    li.addEventListener('dragstart', () => { dragFrom = i; li.classList.add('dragging'); });
    li.addEventListener('dragend', () => { dragFrom = null; li.classList.remove('dragging'); });
    li.addEventListener('dragover', (e) => { e.preventDefault(); li.classList.add('drop-target'); });
    li.addEventListener('dragleave', () => li.classList.remove('drop-target'));
    li.addEventListener('drop', (e) => {
      e.preventDefault(); li.classList.remove('drop-target');
      if (dragFrom !== null && dragFrom !== i) { config.pinned = move(config.pinned, dragFrom, i); renderPinned(); }
    });

    li.append(handle, icon, title, up, down, remove);
    return li;
  }));
}

// ---------- ALL APPS ----------
function renderFilterChips() {
  appsFilterEl.replaceChildren(...APP_FILTERS.map((f) => {
    const chip = document.createElement('button');
    chip.className = 'chip' + (appsState.type === f.value ? ' active' : '');
    chip.textContent = f.label;
    chip.addEventListener('click', () => { appsState.type = f.value; renderFilterChips(); renderApps(); });
    return chip;
  }));
}

function renderApps() {
  const rows = filterItems(allItems, appsState);
  appsCountEl.textContent = `${rows.length} item${rows.length === 1 ? '' : 's'}`;
  appsListEl.replaceChildren(...rows.map((item) => {
    const li = document.createElement('li');
    li.className = 'app-row';

    const icon = iconEl(item.icon, item.type);
    const title = document.createElement('span');
    title.className = 'row-title'; title.textContent = item.title;
    const sub = document.createElement('span');
    sub.className = 'row-sub'; sub.textContent = item.subtitle || item.type;

    const pinned = isPinned(config.pinned, item);
    const btn = document.createElement('button');
    btn.className = 'pin-btn' + (pinned ? ' pinned' : '');
    btn.textContent = pinned ? '✓ Pinned' : '+ Pin';
    btn.addEventListener('click', () => {
      if (isPinned(config.pinned, item)) {
        const k = pinKey(item);
        config.pinned = config.pinned.filter((e) => pinKey(e) !== k);
      } else {
        config.pinned.push({ type: item.type, title: item.title, subtitle: item.subtitle || '', target: item.target });
      }
      renderApps();
      renderPinned();
    });

    li.append(icon, title, sub, btn);
    return li;
  }));
}

appsSearchEl.addEventListener('input', () => { appsState.query = appsSearchEl.value; renderApps(); });

// ---------- save ----------
saveBtn.addEventListener('click', async () => {
  config = await window.nautilus.saveConfig(config);
  renderSections();
  renderPinned();
  renderApps();
  saveStatus.textContent = '✓ Saved';
  setTimeout(() => { saveStatus.textContent = ''; }, 1500);
});

// ---------- init ----------
(async function init() {
  const [cfg, items] = await Promise.all([
    window.nautilus.getConfig(),
    window.nautilus.listIndex(),
  ]);
  config = cfg;
  allItems = items || [];
  for (const it of allItems) if (it.icon) keyIcon.set(pinKey(it), it.icon);
  renderSections();
  renderPinned();
  renderFilterChips();
  renderApps();
  activateTab('home');
})();
