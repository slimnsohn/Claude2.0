'use strict';

const queryEl = document.getElementById('query');
const resultsEl = document.getElementById('results');
const errorEl = document.getElementById('error');

let rows = [];          // [{kind:'header',label} | {kind:'item',item}]
let selectedIndex = -1; // index into rows; points at an item, or -1
let errorTimer = null;

const BADGE_LABEL = { app: 'APP', site: 'SITE', folder: 'FOLDER', claude: 'CLAUDE', calc: 'CALC' };

function faviconUrl(target) {
  try {
    return `https://www.google.com/s2/favicons?domain=${new URL(target).hostname}&sz=32`;
  } catch {
    return null;
  }
}

function iconOrBadge(item) {
  const badge = document.createElement('span');
  badge.className = `badge ${item.type}`;
  badge.textContent = BADGE_LABEL[item.type] || '?';

  const src = item.icon || (item.type === 'site' ? faviconUrl(item.target) : null);
  if (!src) return badge;

  const img = document.createElement('img');
  img.className = 'icon';
  img.src = src;
  img.addEventListener('error', () => img.replaceWith(badge));
  return img;
}

function itemIndices() {
  const idxs = [];
  rows.forEach((r, i) => { if (r.kind === 'item') idxs.push(i); });
  return idxs;
}

function selectFirstItem() {
  selectedIndex = rows.findIndex((r) => r.kind === 'item');
}

function moveSelection(delta) {
  const idxs = itemIndices();
  if (!idxs.length) return;
  const pos = idxs.indexOf(selectedIndex);
  const next = pos === -1 ? (delta > 0 ? 0 : idxs.length - 1)
                          : (pos + delta + idxs.length) % idxs.length;
  selectedIndex = idxs[next];
  render();
}

function render() {
  resultsEl.replaceChildren(
    ...rows.map((row, i) => {
      if (row.kind === 'header') {
        const li = document.createElement('li');
        li.className = 'section-label';
        li.textContent = row.label;
        return li;
      }
      const item = row.item;
      const li = document.createElement('li');
      if (i === selectedIndex) li.classList.add('selected');

      const title = document.createElement('span');
      title.className = 'title';
      title.textContent = item.title;

      const subtitle = document.createElement('span');
      subtitle.className = 'subtitle';
      subtitle.textContent = item.subtitle || '';

      li.append(iconOrBadge(item), title, subtitle);
      li.addEventListener('mousemove', () => {
        if (selectedIndex !== i) { selectedIndex = i; render(); }
      });
      li.addEventListener('click', () => launch(item));
      return li;
    })
  );
  const selected = resultsEl.children[selectedIndex];
  if (selected) selected.scrollIntoView({ block: 'nearest' });
}

function flashError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => { errorEl.hidden = true; }, 2500);
}

let seq = 0; // shared between search() and showHome() so stale responses drop

async function search(value) {
  const mine = ++seq;
  const response = await window.nautilus.search(value);
  if (mine !== seq) return;
  rows = response.results.map((item) => ({ kind: 'item', item }));
  selectFirstItem();
  render();
}

async function showHome() {
  const mine = ++seq;
  const home = await window.nautilus.getHome();
  if (mine !== seq) return;
  rows = home;
  selectFirstItem();
  render();
}

function onQueryChanged() {
  if (queryEl.value.trim() === '') showHome();
  else search(queryEl.value);
}

async function launch(item) {
  if (!item) return;
  if (item.type === 'calc' && !item.target) return; // mid-typing — ignore Enter
  const result = await window.nautilus.launch(item);
  if (!result.ok) flashError(`Couldn't launch ${item.title}: ${result.error}`);
}

queryEl.addEventListener('input', onQueryChanged);

queryEl.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
    e.preventDefault();
    moveSelection(1);
  } else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
    e.preventDefault();
    moveSelection(-1);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const row = rows[selectedIndex];
    if (row && row.kind === 'item') launch(row.item);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    window.nautilus.hide();
  }
});

window.nautilus.onShown(() => {
  queryEl.value = '';
  errorEl.hidden = true;
  showHome();
  requestAnimationFrame(() => queryEl.focus());
});

// Initial focus + home for the first show (window:shown may fire before load).
queryEl.focus();
showHome();
