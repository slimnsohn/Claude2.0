'use strict';

const queryEl = document.getElementById('query');
const resultsEl = document.getElementById('results');
const errorEl = document.getElementById('error');

let results = [];
let selectedIndex = 0;
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

function render() {
  resultsEl.replaceChildren(
    ...results.map((item, i) => {
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
      li.addEventListener('click', () => launch(results[i]));
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

let searchSeq = 0;

async function search(value) {
  const seq = ++searchSeq;
  const response = await window.nautilus.search(value);
  if (seq !== searchSeq) return; // a newer query is in flight — drop stale results
  results = response.results;
  selectedIndex = 0;
  render();
}

async function launch(item) {
  if (!item) return;
  if (item.type === 'calc' && !item.target) return; // mid-typing — ignore Enter
  const result = await window.nautilus.launch(item);
  if (!result.ok) flashError(`Couldn't launch ${item.title}: ${result.error}`);
}

queryEl.addEventListener('input', () => search(queryEl.value));

queryEl.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
    e.preventDefault();
    if (results.length) { selectedIndex = (selectedIndex + 1) % results.length; render(); }
  } else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
    e.preventDefault();
    if (results.length) { selectedIndex = (selectedIndex - 1 + results.length) % results.length; render(); }
  } else if (e.key === 'Enter') {
    e.preventDefault();
    launch(results[selectedIndex]);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    window.nautilus.hide();
  }
});

window.nautilus.onShown(() => {
  queryEl.value = '';
  results = [];
  selectedIndex = 0;
  errorEl.hidden = true;
  render();
  requestAnimationFrame(() => queryEl.focus());
});

// Initial focus for the first show (window:shown may fire before load).
queryEl.focus();
