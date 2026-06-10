/* Polymarket Trader dashboard — vanilla JS, WS push + REST pulls. */
(() => {
  const $ = (id) => document.getElementById(id);
  let controlToken = localStorage.getItem("pmtrader_token") || "";

  // ---- state via websocket -------------------------------------------------
  function connectWS() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (ev) => renderState(JSON.parse(ev.data));
    ws.onclose = () => setTimeout(connectWS, 3000);
  }

  function fmtMoney(x) {
    return "$" + Number(x).toLocaleString(undefined,
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function shortTok(t) {
    return t.length > 14 ? t.slice(0, 6) + "…" + t.slice(-6) : t;
  }

  function renderState(s) {
    $("equity").textContent = fmtMoney(s.equity);
    $("equity").style.color = s.equity >= s.bankroll_start ?
      "var(--green)" : "var(--red)";
    $("cash").textContent = `cash ${fmtMoney(s.cash)} · start ${fmtMoney(s.bankroll_start)}`;
    $("n-markets").textContent = s.n_markets;
    $("last-update").textContent = new Date(s.ts * 1000).toLocaleTimeString();

    const pill = $("mode-pill");
    pill.textContent = s.mode.toUpperCase();
    pill.className = `pill ${s.mode}`;
    $("halt-pill").classList.toggle("hidden", !s.halted);
    $("halt-pill").textContent = s.halted ?
      `HALTED${s.stop_reason ? ": " + s.stop_reason : ""}` : "";
    $("resume-btn").classList.toggle("hidden", !s.halted);
    $("kill-btn").classList.toggle("hidden", s.halted);

    if (s.double_or_bust) {
      $("progress-bar").style.width = `${s.bankroll_progress * 100}%`;
      $("progress-label").textContent =
        `${(s.bankroll_progress * 100).toFixed(1)}% to double ` +
        `(${fmtMoney(s.equity)} / ${fmtMoney(s.bankroll_start * 2)})`;
    } else {
      $("progress-label").textContent = "double-or-bust mode off";
    }

    renderRows("positions-table", s.positions.map(p => [
      ["mono", shortTok(p.token_id)], ["", p.size], ["", p.avg_cost],
      ["", p.mark], [p.unrealized >= 0 ? "pos" : "neg", fmtMoney(p.unrealized)],
    ]));
    renderRows("orders-table", s.open_orders.map(o => [
      ["", o.strategy], ["mono", shortTok(o.token_id)], ["", o.side],
      ["", o.price.toFixed(3)], ["", o.size], ["", o.filled],
      ["", o.status],
    ]));
  }

  function renderRows(tableId, rows) {
    const tbody = $(tableId).querySelector("tbody");
    tbody.innerHTML = "";
    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="9" class="sub">— none —</td>`;
      tbody.appendChild(tr);
      return;
    }
    for (const cells of rows) {
      const tr = document.createElement("tr");
      for (const [cls, text] of cells) {
        const td = document.createElement("td");
        if (cls) td.className = cls;
        td.textContent = text;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }

  // ---- strategies + decisions + equity (polled) ------------------------------
  async function poll() {
    try {
      const [stratR, decR, eqR] = await Promise.all([
        fetch("/api/strategies"),
        fetch(`/api/decisions?limit=80${decisionFilter() ? "&strategy=" + decisionFilter() : ""}`),
        fetch("/api/equity"),
      ]);
      renderStrategies(await stratR.json());
      renderDecisions(await decR.json());
      drawEquity(await eqR.json());
    } catch (e) { /* server briefly away; ws handles reconnect UX */ }
    setTimeout(poll, 5000);
  }

  function decisionFilter() {
    return $("decision-filter").value;
  }

  function renderStrategies(rows) {
    renderRows("strategies-table", rows.map(s => [
      ["", s.name], [`gate-${s.gate}`, s.gate],
      ["", (s.weight * 100).toFixed(1) + "%"], ["", fmtMoney(s.budget)],
      ["", s.n_paper_trades], ["", s.n_live_trades],
    ]));
  }

  function renderDecisions(rows) {
    renderRows("decisions-table", rows.map(d => {
      const p = d.payload || {};
      const detail = p.detail || p.rule || p.reason || JSON.stringify(p);
      return [
        ["sub", new Date(d.ts * 1000).toLocaleTimeString()],
        ["", d.strategy], [`kind-${d.kind}`, d.kind], ["mono", detail],
      ];
    }));
  }

  // ---- equity chart (hand-rolled canvas, no deps) -------------------------------
  function drawEquity(points) {
    const canvas = $("equity-chart");
    const ctx = canvas.getContext("2d");
    const W = canvas.width = canvas.clientWidth;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    if (points.length < 2) {
      ctx.fillStyle = "#8b949e";
      ctx.fillText("collecting data…", 10, H / 2);
      return;
    }
    const eq = points.map(p => p.equity);
    const lo = Math.min(...eq) * 0.998, hi = Math.max(...eq) * 1.002;
    const x = (i) => (i / (points.length - 1)) * (W - 20) + 10;
    const y = (v) => H - 14 - ((v - lo) / (hi - lo || 1)) * (H - 28);
    ctx.strokeStyle = eq[eq.length - 1] >= eq[0] ? "#3fb950" : "#f85149";
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, i) => i ? ctx.lineTo(x(i), y(p.equity))
                               : ctx.moveTo(x(i), y(p.equity)));
    ctx.stroke();
    ctx.fillStyle = "#8b949e";
    ctx.font = "11px Consolas";
    ctx.fillText(hi.toFixed(2), 10, 12);
    ctx.fillText(lo.toFixed(2), 10, H - 4);
  }

  // ---- controls ------------------------------------------------------------------
  function ensureToken() {
    if (!controlToken) {
      controlToken = prompt("Control token (from config/settings.yaml):") || "";
      localStorage.setItem("pmtrader_token", controlToken);
    }
    return controlToken;
  }

  async function control(path) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: ensureToken() }),
    });
    if (r.status === 403) {
      localStorage.removeItem("pmtrader_token");
      controlToken = "";
      alert("Bad control token.");
    }
  }

  $("kill-btn").onclick = () => {
    if (confirm("Cancel all orders and halt trading?")) control("/api/control/kill");
  };
  $("resume-btn").onclick = () => control("/api/control/resume");
  $("decision-filter").onchange = () => {};

  connectWS();
  poll();
})();
