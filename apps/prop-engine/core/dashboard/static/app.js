const state = { plays: [], bets: [] };

function american(odds) {
  return odds >= 0 ? `+${odds}` : `${odds}`;
}

function fmtPct(p) {
  return (p * 100).toFixed(1) + "%";
}

function $(sel) { return document.querySelector(sel); }
function el(tag, props = {}, kids = []) {
  const n = document.createElement(tag);
  Object.assign(n, props);
  for (const k of kids) n.appendChild(typeof k === "string" ? document.createTextNode(k) : k);
  return n;
}

async function loadPlays() {
  const r = await fetch("/api/plays");
  const data = await r.json();
  state.plays = data.plays || [];
  $("#meta").textContent = `Run ${data.run_id ?? "?"} · ${data.n_plays ?? 0} plays · generated ${data.generated_at ?? ""}`;
  renderBoard();
}

async function loadBets() {
  const r = await fetch("/api/bets");
  const data = await r.json();
  state.bets = data.bets || [];
  renderBets();
}

function applyFilters(plays) {
  const minEdge = parseFloat($("#filter-edge").value) || 0;
  const stat = $("#filter-stat").value;
  const books = [...$("#filter-book").selectedOptions].map((o) => o.value);
  return plays.filter(p =>
    p.edge_pct >= minEdge &&
    (!stat || p.market_type === stat) &&
    books.includes(p.book)
  );
}

function renderBoard() {
  const board = $("#board");
  board.innerHTML = "";
  const filtered = applyFilters(state.plays).sort((a, b) => b.edge_pct - a.edge_pct);
  if (!filtered.length) {
    board.appendChild(el("p", { className: "empty" }, ["No plays match filters."]));
    return;
  }
  const headers = ["Player", "Stat", "Line", "Side", "Book", "Odds", "Posterior", "Edge", "Stake", "EV $", ""];
  const table = el("table", { className: "board" });
  const thead = el("thead", {}, [el("tr", {}, headers.map(h => el("th", {}, [h])))]);
  const tbody = el("tbody");
  for (const p of filtered) {
    const tr = el("tr", {});
    tr.appendChild(el("td", {}, [p.player_name]));
    tr.appendChild(el("td", {}, [p.market_type.replace("player_", "")]));
    tr.appendChild(el("td", {}, [String(p.line_value)]));
    tr.appendChild(el("td", {}, [p.side]));
    tr.appendChild(el("td", {}, [p.book]));
    tr.appendChild(el("td", {}, [american(p.offered_odds)]));
    tr.appendChild(el("td", {}, [fmtPct(p.posterior_prob)]));
    tr.appendChild(el("td", { className: "edge" }, [fmtPct(p.edge_pct)]));
    tr.appendChild(el("td", {}, [`$${Number(p.recommended_stake).toFixed(2)}`]));
    tr.appendChild(el("td", {}, [`$${Number(p.ev_dollars).toFixed(2)}`]));
    const btn = el("button", { className: "log-btn" }, ["Log bet"]);
    btn.addEventListener("click", () => promptLogBet(p));
    tr.appendChild(el("td", {}, [btn]));
    tbody.appendChild(tr);
  }
  table.appendChild(thead);
  table.appendChild(tbody);
  board.appendChild(table);
}

function renderBets() {
  const node = $("#bets");
  node.innerHTML = "";
  if (!state.bets.length) {
    node.appendChild(el("p", { className: "empty" }, ["No bets logged yet."]));
    return;
  }
  const headers = ["Placed", "Book", "Stake", "Odds", "Result", "Profit"];
  const table = el("table", { className: "bets" });
  table.appendChild(el("thead", {}, [el("tr", {}, headers.map(h => el("th", {}, [h])))]));
  const tbody = el("tbody");
  for (const b of state.bets) {
    const tr = el("tr", {});
    tr.appendChild(el("td", {}, [String(b.placed_at)]));
    tr.appendChild(el("td", {}, [b.book]));
    tr.appendChild(el("td", {}, [`$${Number(b.stake_actual).toFixed(2)}`]));
    tr.appendChild(el("td", {}, [american(b.odds_actual)]));
    tr.appendChild(el("td", {}, [b.result || "—"]));
    tr.appendChild(el("td", {}, [b.profit != null ? `$${Number(b.profit).toFixed(2)}` : "—"]));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  node.appendChild(table);
}

async function promptLogBet(play) {
  const recommended = Number(play.recommended_stake).toFixed(2);
  const stake = prompt(`Stake amount in $ (recommended: ${recommended}):`, recommended);
  if (!stake) return;
  const r = await fetch("/api/log_bet", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      play_id: play.id, stake_actual: parseFloat(stake),
      odds_actual: play.offered_odds, book: play.book,
    }),
  });
  if (r.ok) {
    alert("Logged.");
    loadPlays();
  } else {
    alert("Failed to log: " + r.status);
  }
}

function setView(name) {
  document.querySelectorAll("nav button[data-view]").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name));
  $("#board").hidden = name !== "board";
  $("#bets").hidden = name !== "bets";
  $("#filters").hidden = name !== "board";
  if (name === "bets") loadBets();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("nav button[data-view]").forEach((b) =>
    b.addEventListener("click", () => setView(b.dataset.view)));
  $("#refresh-btn").addEventListener("click", async () => {
    $("#refresh-btn").disabled = true;
    $("#refresh-btn").textContent = "Refreshing…";
    try {
      await fetch("/api/refresh", { method: "POST" });
      await loadPlays();
    } finally {
      $("#refresh-btn").disabled = false;
      $("#refresh-btn").textContent = "Refresh slate";
    }
  });
  ["filter-edge", "filter-stat", "filter-book"].forEach((id) =>
    $("#" + id).addEventListener("change", renderBoard));
  loadPlays();
});
