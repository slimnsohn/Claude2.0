'use strict';

const SECTIONS = [
  { key: 'pinned', label: 'Pinned' },
  { key: 'recent', label: 'Recent' },
  { key: 'frequent', label: 'Frequent' },
];
const TYPE_OPTIONS = [
  { value: 'all', label: 'All types' },
  { value: 'app', label: 'Apps' },
  { value: 'folder', label: 'Folders' },
  { value: 'site', label: 'Sites' },
];

let config = null;

const sectionRowsEl = document.getElementById('section-rows');
const pinnedListEl = document.getElementById('pinned-list');
const pinSearchEl = document.getElementById('pin-search');
const pinResultsEl = document.getElementById('pin-results');
const saveBtn = document.getElementById('save-btn');
const saveStatus = document.getElementById('save-status');

function key(entry) { return `${entry.type}:${entry.target}`; }

function renderSections() {
  sectionRowsEl.replaceChildren(...SECTIONS.map(({ key: k, label }) => {
    const cfg = config.sections[k];
    const row = document.createElement('div');
    row.className = 'section-row';

    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.checked = cfg.enabled;
    enabled.addEventListener('change', () => { cfg.enabled = enabled.checked; });

    const name = document.createElement('span');
    name.className = 'section-name';
    name.textContent = label;

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

    const enableLabel = document.createElement('label');
    enableLabel.className = 'enable-label';
    enableLabel.append(enabled, name);

    row.append(enableLabel, type, limit);
    return row;
  }));
}

function renderPinned() {
  pinnedListEl.replaceChildren(...config.pinned.map((entry, i) => {
    const li = document.createElement('li');

    const title = document.createElement('span');
    title.className = 'pin-title';
    title.textContent = entry.title;

    const up = document.createElement('button');
    up.textContent = '↑'; up.disabled = i === 0;
    up.addEventListener('click', () => { swap(i, i - 1); });

    const down = document.createElement('button');
    down.textContent = '↓'; down.disabled = i === config.pinned.length - 1;
    down.addEventListener('click', () => { swap(i, i + 1); });

    const remove = document.createElement('button');
    remove.textContent = '✕';
    remove.addEventListener('click', () => { config.pinned.splice(i, 1); renderPinned(); });

    li.append(title, up, down, remove);
    return li;
  }));
}

function swap(a, b) {
  const p = config.pinned;
  [p[a], p[b]] = [p[b], p[a]];
  renderPinned();
}

let searchSeq = 0;
async function searchToPin(value) {
  if (value.trim() === '') { pinResultsEl.replaceChildren(); return; }
  const mine = ++searchSeq;
  const { results } = await window.nautilus.searchIndex(value);
  if (mine !== searchSeq) return;
  const pinnable = results.filter((r) => ['app', 'folder', 'site'].includes(r.type));
  pinResultsEl.replaceChildren(...pinnable.map((item) => {
    const li = document.createElement('li');
    li.textContent = item.title;
    const already = config.pinned.some((e) => key(e) === `${item.type}:${item.target}`);
    if (already) { li.className = 'pinned-already'; }
    li.addEventListener('click', () => {
      if (config.pinned.some((e) => key(e) === `${item.type}:${item.target}`)) return;
      config.pinned.push({ type: item.type, title: item.title, subtitle: item.subtitle || '', target: item.target });
      renderPinned();
      searchToPin(pinSearchEl.value);
    });
    return li;
  }));
}

pinSearchEl.addEventListener('input', () => searchToPin(pinSearchEl.value));

saveBtn.addEventListener('click', async () => {
  config = await window.nautilus.saveConfig(config);
  renderSections();
  renderPinned();
  saveStatus.textContent = 'Saved';
  setTimeout(() => { saveStatus.textContent = ''; }, 1500);
});

(async function init() {
  config = await window.nautilus.getConfig();
  renderSections();
  renderPinned();
})();
