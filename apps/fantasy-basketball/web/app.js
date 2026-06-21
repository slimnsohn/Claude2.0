"use strict";
const CATS = ["FG_PCT","FT_PCT","FG3M","PTS","REB","AST","STL","BLK","TOV"];
const CAT_LABEL = {FG_PCT:"FG%",FT_PCT:"FT%",FG3M:"3PM",PTS:"PTS",REB:"REB",AST:"AST",STL:"STL",BLK:"BLK",TOV:"TO"};

const $ = (s, r=document) => r.querySelector(s);
const el = (h) => { const t=document.createElement("template"); t.innerHTML=h.trim(); return t.content.firstChild; };
const fmt = (v,d=1) => (v===null||v===undefined||v==="")?"–":(typeof v==="number"?v.toFixed(d):v);
const api = async (u,opt) => (await fetch(u,opt)).json();
const z = (v) => `<span class="${v>0?'posv':(v<0?'neg':'')}">${v>0?'+':''}${v.toFixed(1)}</span>`;
const loading = (n) => `<div class="loading">Loading ${n}…</div>`;

// ---- routing ----
const views = {};
let loaded = {};
document.querySelectorAll(".tabs a").forEach(a => a.onclick = () => show(a.dataset.view));
function show(name){
  document.querySelectorAll(".tabs a").forEach(a=>a.classList.toggle("active",a.dataset.view===name));
  document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));
  $("#"+name).classList.remove("hidden");
  if(!loaded[name]){ loaded[name]=true; views[name](); }
}

// ============ OVERVIEW ============
views.overview = async () => {
  const root = $("#overview"); root.innerHTML = loading("overview");
  const d = await api("/api/overview");
  const lake = d.lake, mt = d.my_team, lg = d.league;
  const range = lake.season_range ? `${lake.season_range[0]} – ${lake.season_range[1]}` : "–";
  root.innerHTML = `
    <h2>Overview</h2>
    <p class="sub">Your fantasy basketball data lake at a glance.</p>
    <div class="cards">
      <div class="card"><div class="n">${lake.game_log_rows.toLocaleString()}</div><div class="l">game-log rows</div></div>
      <div class="card"><div class="n">${lake.seasons}</div><div class="l">seasons (${range})</div></div>
      <div class="card"><div class="n">${lake.players.toLocaleString()}</div><div class="l">players</div></div>
      <div class="card"><div class="n">${lake.teams}</div><div class="l">NBA teams</div></div>
    </div>
    <div class="cards">
      ${mt?`<div class="card link" data-go="league"><div class="n">${mt.name}</div><div class="l">your team · ${mt.roster_size} players</div></div>`:""}
      <div class="card link" data-go="league"><div class="n">${lg.history_seasons}</div><div class="l">seasons of league history</div></div>
      <div class="card link" data-go="league"><div class="n">${lg.owners}</div><div class="l">all-time owners</div></div>
      <div class="card link" data-go="draft"><div class="n">Draft →</div><div class="l">projected board + live cockpit</div></div>
    </div>`;
  root.querySelectorAll("[data-go]").forEach(c=>c.onclick=()=>show(c.dataset.go));
};

// ============ PLAYERS (with accordion) ============
views.players = async () => {
  const root = $("#players");
  root.innerHTML = `<h2>Players</h2><p class="sub">Ranked by last season's 9-cat value. Click a player to see every season.</p>
    <div class="controls"><div class="acwrap">
      <input type="text" class="search" id="psearch" placeholder="Search players… (3+ letters for suggestions)" autocomplete="off">
      <div id="acdrop" class="ac hidden"></div></div></div>
    <div id="ptable">${loading("players")}</div>`;
  const input = $("#psearch"), drop = $("#acdrop");
  const render = async (q) => {
    const rows = await api("/api/players?search="+encodeURIComponent(q||""));
    $("#ptable").innerHTML = playerTable(rows);
    bindAccordion($("#ptable"));
  };
  const suggest = async (q) => {
    if(q.length < 3){ drop.classList.add("hidden"); return; }
    const rows = await api("/api/players?search="+encodeURIComponent(q));
    if(!rows.length){ drop.classList.add("hidden"); return; }
    drop.innerHTML = rows.slice(0,8).map(r=>`<div class="acitem" data-name="${r.full_name.replace(/"/g,'&quot;')}">
      <span class="name">${r.full_name}</span><span class="muted">${r.nba_position||''} · #${r.rank??'–'}</span></div>`).join("");
    drop.classList.remove("hidden");
    drop.querySelectorAll(".acitem").forEach(it=>it.onclick=()=>{ input.value=it.dataset.name; drop.classList.add("hidden"); render(it.dataset.name); });
  };
  let t;
  input.oninput = () => { const q=input.value.trim(); clearTimeout(t); t=setTimeout(()=>{ render(q); suggest(q); },180); };
  input.onblur = () => setTimeout(()=>drop.classList.add("hidden"), 150);
  input.onfocus = () => { const q=input.value.trim(); if(q.length>=3) suggest(q); };
  render("");
};
function statHead(){ return ["GP","PPG","REB","AST","STL","BLK","3PM","FG%","FT%"].map(h=>`<th>${h}</th>`).join(""); }
function statCells(r){ return `
  <td>${r.gp??"–"}</td><td>${fmt(r.ppg)}</td><td>${fmt(r.rpg)}</td><td>${fmt(r.apg)}</td>
  <td>${fmt(r.spg)}</td><td>${fmt(r.bpg)}</td><td>${fmt(r.tpm_pg)}</td>
  <td>${fmt(r.fg_pct,3)}</td><td>${fmt(r.ft_pct,3)}</td>`; }
function playerTable(rows){
  return `<table><thead><tr><th>#</th><th class="l">Player</th><th class="l">Pos</th><th class="l">Team</th>${statHead()}</tr></thead>
    <tbody>${rows.map(r=>`
      <tr class="clickable" data-pid="${r.player_id}">
        <td class="muted">${r.rank??"–"}</td><td class="l name">${r.full_name}</td><td class="l pos">${r.nba_position||"–"}</td>
        <td class="l pos">${r.team||"–"}</td>${statCells(r)}</tr>`).join("")}
    </tbody></table>`;
}
function bindAccordion(scope){
  scope.querySelectorAll("tr.clickable").forEach(tr=>tr.onclick=async ()=>{
    const next = tr.nextElementSibling;
    if(next && next.classList.contains("accordion")){ next.remove(); return; }
    const seasons = await api(`/api/player/${tr.dataset.pid}/seasons`);
    const inner = `<div class="inner"><h4>Season history</h4><table><thead>
      <tr><th class="l">Season</th>${statHead()}</tr></thead><tbody>
      ${seasons.map(s=>`<tr><td class="l">${s.season}</td>${statCells(s)}</tr>`).join("")}
      </tbody></table></div>`;
    const span = 13;  // #, Player, Pos, Team + 9 stat cols
    tr.after(el(`<tr class="accordion"><td colspan="${span}">${inner}</td></tr>`));
  });
}

// ============ RANKINGS ============
function puntChips(state){
  return `<div class="chips">${CATS.map(c=>`<span class="chip ${state.has(c)?'on':''}" data-cat="${c}">${CAT_LABEL[c]}</span>`).join("")}</div>`;
}
function zTable(rows, posRank){
  return `<table><thead><tr><th>#</th><th class="l">Player</th><th class="l">Pos</th>
    ${CATS.map(c=>`<th>${CAT_LABEL[c]}</th>`).join("")}<th>TOTAL</th></tr></thead><tbody>
    ${rows.map(r=>`<tr><td>${r.rank}</td><td class="l name">${r.full_name}</td>
      <td class="l ${posRank?'pos-rank':'pos'}">${posRank?r.pos_rank:(r.nba_position||"–")}</td>
      ${CATS.map(c=>`<td>${z(r.zscores[c])}</td>`).join("")}
      <td><b>${r.total_value.toFixed(1)}</b></td></tr>`).join("")}
    </tbody></table>`;
}
views.rankings = async () => {
  const root = $("#rankings");
  const punt = new Set();
  root.innerHTML = `<h2>Rankings</h2><p class="sub">9-cat z-score value vs the player pool. Percentages are volume-weighted.</p>
    <div class="controls">
      <span><label>Value</label><select id="rsource">
        <option value="season">Last season</option><option value="recent">Recent form</option>
        <option value="projection">Projected next season</option></select></span>
      <span><label>Pos</label><select id="rpos"><option value="">All</option>
        <option>G</option><option>F</option><option>C</option></select></span>
      <span><label>Punt</label>${puntChips(punt)}</span>
    </div>
    <div id="rtable">${loading("rankings")}</div>`;
  const render = async () => {
    const src = $("#rsource").value, pos = $("#rpos").value;
    let u = `/api/rankings?source=${src}`+(pos?`&pos=${pos}`:"");
    punt.forEach(c=>u+=`&punt=${c}`);
    $("#rtable").innerHTML = loading("rankings");
    $("#rtable").innerHTML = zTable((await api(u)).slice(0,200), false);
  };
  root.querySelector("#rsource").onchange = render;
  root.querySelector("#rpos").onchange = render;
  root.querySelectorAll(".chip").forEach(ch=>ch.onclick=()=>{
    const c=ch.dataset.cat; ch.classList.toggle("on"); punt.has(c)?punt.delete(c):punt.add(c); render();
  });
  render();
};

// ============ DRAFT COCKPIT ============
views.draft = async () => {
  const root = $("#draft");
  const punt = new Set();
  const drafted = new Set(), mine = [];
  root.innerHTML = `<h2>Draft</h2><p class="sub">Projected board with live tracking. Mark players as they go; ★ for your picks.</p>
    <div class="controls">
      <span><label>Value</label><select id="dsource">
        <option value="projection">Projected next season</option><option value="season">Last season</option>
        <option value="recent">Recent form</option></select></span>
      <span><label>Pos</label><select id="dpos"><option value="">All</option><option>G</option><option>F</option><option>C</option></select></span>
      <span><label>Punt</label>${puntChips(punt)}</span>
      <button class="ghost" id="dreset">Reset draft</button>
    </div>
    <div class="cockpit"><div id="dboard">${loading("board")}</div>
    <div class="panel" id="dpanel"></div></div>`;
  let board = [];
  const opts = () => ({source:$("#dsource").value, pos:$("#dpos").value, punt:[...punt]});

  const loadBoard = async () => {
    const o = opts(); let u = `/api/draft/board?source=${o.source}`+(o.pos?`&pos=${o.pos}`:"");
    o.punt.forEach(c=>u+=`&punt=${c}`);
    $("#dboard").innerHTML = loading("board");
    board = await api(u); drawBoard(); drawPanel();
  };
  const drawBoard = () => {
    let lastTier=null, html=`<table><thead><tr><th>#</th><th class="l">Player</th><th class="l">Pos</th><th>TOT</th><th></th></tr></thead><tbody>`;
    board.forEach(p=>{
      if(drafted.has(p.player_id)) return;
      if(p.tier!==lastTier){ lastTier=p.tier; html+=`<tr class="tierhead"><td></td><td class="l" colspan="4">Tier ${p.tier}</td></tr>`; }
      html+=`<tr><td>${p.rank}</td><td class="l name">${p.full_name}</td>
        <td class="l pos-rank">${p.pos_rank}</td><td><b>${p.total_value.toFixed(1)}</b></td>
        <td><span class="rowbtns"><button class="mini" data-took="${p.player_id}">took</button>
        <button class="mini star" data-mine="${p.player_id}">★</button></span></td></tr>`;
    });
    $("#dboard").innerHTML = html+"</tbody></table>";
    $("#dboard").querySelectorAll("[data-took]").forEach(b=>b.onclick=()=>{drafted.add(+b.dataset.took); drawBoard(); drawPanel();});
    $("#dboard").querySelectorAll("[data-mine]").forEach(b=>b.onclick=()=>{const id=+b.dataset.mine; drafted.add(id); mine.push(id); drawBoard(); drawPanel();});
  };
  const drawPanel = async () => {
    const byId = Object.fromEntries(board.map(p=>[p.player_id,p]));
    const roster = mine.map(id=>byId[id]).filter(Boolean);
    let html = `<h3>Your roster (${roster.length})</h3>`;
    html += roster.length? `<table><tbody>${roster.map(p=>`<tr><td class="l name">${p.full_name}</td><td>${p.total_value.toFixed(1)}</td></tr>`).join("")}</tbody></table>`
                         : `<p class="muted">No picks yet. Hit ★ on your players.</p>`;
    $("#dpanel").innerHTML = html + `<div id="recs"></div>`;
    const o = opts();
    const rec = await api("/api/draft/recommend",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({drafted_ids:[...drafted], my_ids:mine, source:o.source, punt:o.punt})});
    const list = roster.length? rec.by_need : rec.available;
    const title = roster.length? "Best for your needs" : "Best available";
    $("#recs").innerHTML = `<h3 style="margin-top:18px">${title}</h3><table><tbody>`+
      list.slice(0,12).map(p=>`<tr><td class="l">${p.full_name}</td><td>${(p.needs_value??p.total_value).toFixed(1)}</td></tr>`).join("")+`</tbody></table>`;
  };
  $("#dsource").onchange=loadBoard; $("#dpos").onchange=loadBoard;
  root.querySelectorAll(".chip").forEach(ch=>ch.onclick=()=>{const c=ch.dataset.cat; ch.classList.toggle("on"); punt.has(c)?punt.delete(c):punt.add(c); loadBoard();});
  $("#dreset").onclick=()=>{drafted.clear(); mine.length=0; drawBoard(); drawPanel();};
  loadBoard();
};

// ============ LEAGUE ============
views.league = async () => {
  const root = $("#league");
  root.innerHTML = `<h2>League — The Best Time of Year</h2><p class="sub">16 seasons of history, 2010–2025.</p>
    <div class="subnav">
      <a data-sub="champions" class="active">Champions</a><a data-sub="owners">Owners</a>
      <a data-sub="standings">Standings</a><a data-sub="draft">Draft history</a><a data-sub="rosters">Current rosters</a>
    </div><div id="lbody">${loading("league")}</div>`;
  const subs = {};
  root.querySelectorAll(".subnav a").forEach(a=>a.onclick=()=>{
    root.querySelectorAll(".subnav a").forEach(x=>x.classList.toggle("active",x===a));
    subs[a.dataset.sub]();
  });

  subs.champions = async () => {
    const d = await api("/api/league/champions");
    $("#lbody").innerHTML = `<table><thead><tr><th class="l">Season</th><th class="l">Champion</th><th class="l">Owner</th><th>Seed</th><th>Reg. rank</th></tr></thead><tbody>
      ${d.map(c=>`<tr><td class="l">${c.season}</td><td class="l name">${c.team_name}</td><td class="l">${c.owner_label||"–"}</td><td>${c.playoff_seed??"–"}</td><td>${c.regular_season_rank??"–"}</td></tr>`).join("")}</tbody></table>`;
  };
  subs.owners = async () => {
    const d = await api("/api/league/owners");
    $("#lbody").innerHTML = `<table><thead><tr><th class="l">Owner</th><th>Titles</th><th>Seasons</th><th>Best finish</th><th class="l">Span</th></tr></thead><tbody>
      ${d.map(o=>`<tr><td class="l name">${o.owner_label}</td><td><b>${o.titles}</b></td><td>${o.seasons}</td><td>${o.best_finish}</td><td class="l muted">${o.first_season}–${o.last_season}</td></tr>`).join("")}</tbody></table>`;
  };
  subs.standings = async () => {
    const seasons = await api("/api/league/seasons");
    const pick = `<div class="controls"><span><label>Season</label><select id="lss">${seasons.map(s=>`<option>${s}</option>`).join("")}</select></span></div>`;
    const draw = async () => {
      const d = await api("/api/league/standings?season="+$("#lss").value);
      $("#stbody").innerHTML = `<table><thead><tr><th>Reg.</th><th>Seed</th><th>Final</th><th class="l">Team</th><th class="l">Owner</th><th class="l">Record</th></tr></thead><tbody>
        ${d.teams.map(t=>`<tr><td>${t.regular_season_rank}</td><td>${t.playoff_seed??"–"}</td><td><b>${t.final_rank}</b></td><td class="l name">${t.team_name}</td><td class="l">${t.owner_label||"–"}</td><td class="l muted">${t.wins}-${t.losses}-${t.ties}</td></tr>`).join("")}</tbody></table>`;
    };
    $("#lbody").innerHTML = pick + `<div id="stbody"></div>`;
    $("#lss").onchange = draw; draw();
  };
  subs.draft = async () => {
    const seasons = await api("/api/league/seasons");
    $("#lbody").innerHTML = `<div class="controls"><span><label>Season</label><select id="lds">${seasons.map(s=>`<option>${s}</option>`).join("")}</select></span></div><div id="ldbody"></div>`;
    const draw = async () => {
      const d = await api("/api/league/draft?season="+$("#lds").value);
      $("#ldbody").innerHTML = `<table><thead><tr><th>Pick</th><th>Rd</th><th class="l">Player</th><th class="l">Team</th><th class="l">Owner</th></tr></thead><tbody>
        ${d.picks.map(p=>`<tr><td>${p.pick}</td><td>${p.round}</td><td class="l name">${p.player_name||"–"}</td><td class="l">${p.team_name||"–"}</td><td class="l muted">${p.owner_label||"–"}</td></tr>`).join("")}</tbody></table>`;
    };
    $("#lds").onchange = draw; draw();
  };
  subs.rosters = async () => {
    const d = await api("/api/league/rosters");
    $("#lbody").innerHTML = d.map(t=>`<div style="margin-bottom:22px"><h3 style="margin:0 0 8px">${t.name}${t.is_my_team?' <span style="color:var(--accent)">· you</span>':''} <span class="muted" style="font-weight:400">— ${t.manager}</span></h3>
      <table><tbody>${t.players.map(p=>`<tr><td class="l name">${p.player_name}</td><td class="l pos">${p.editorial_team||""}</td><td class="l pos">${p.eligible_positions||""}</td><td class="l">${p.status?('<span class="neg">'+p.status+'</span>'):''}</td></tr>`).join("")}</tbody></table></div>`).join("");
  };
  subs.champions();
};

// ============ UPDATE ============
views.update = async () => {
  const root = $("#update");
  const draw = async () => {
    const s = await api("/api/update/state");
    const updated = s.last_updated ? s.last_updated.split(".")[0] : "never";
    root.innerHTML = `
      <h2>Update data</h2>
      <p class="sub">Run this in the offseason or before your draft to pull last year's stats, ages, and Yahoo data. Idempotent — safe to run anytime.</p>
      <div class="cards">
        <div class="card"><div class="n">${s.latest_season||"–"}</div><div class="l">latest season loaded</div></div>
        <div class="card"><div class="n">${(s.game_log_rows||0).toLocaleString()}</div><div class="l">game-log rows</div></div>
        <div class="card"><div class="n">${s.history_seasons}</div><div class="l">league history seasons</div></div>
        <div class="card"><div class="n" style="font-size:15px">${updated}</div><div class="l">last updated</div></div>
      </div>
      <div class="controls">
        <button class="btn" id="uall">Refresh everything</button>
        <a id="uadv" class="muted" style="cursor:pointer">Advanced ▾</a>
      </div>
      <div id="usteps" class="hidden" style="margin:-8px 0 18px">
        <div class="chips">${s.steps.map(st=>`<label class="chip on" data-step="${st.key}"><input type="checkbox" checked style="margin-right:6px">${st.label}</label>`).join("")}</div>
        <button class="ghost" id="urun" style="margin-top:12px">Run selected</button>
      </div>
      <div id="uprogress"></div>
      <pre id="ulog" class="ulog hidden"></pre>`;

    const advBox = $("#usteps");
    $("#uadv").onclick = () => advBox.classList.toggle("hidden");
    advBox.querySelectorAll(".chip").forEach(ch => ch.onclick = (e) => {
      if(e.target.tagName!=="INPUT"){ const c=ch.querySelector("input"); c.checked=!c.checked; }
      ch.classList.toggle("on", ch.querySelector("input").checked);
    });
    const allKeys = s.steps.map(st=>st.key);
    const labels = Object.fromEntries(s.steps.map(st=>[st.key,st.label]));
    $("#uall").onclick = () => runRefresh(allKeys, labels);
    $("#urun").onclick = () => {
      const sel = [...advBox.querySelectorAll(".chip")].filter(c=>c.querySelector("input").checked).map(c=>c.dataset.step);
      if(sel.length) runRefresh(sel, labels);
    };
  };

  const runRefresh = (steps, labels) => {
    document.querySelectorAll("#uall,#urun").forEach(b=>b.disabled=true);
    const prog = $("#uprogress"), log = $("#ulog");
    log.textContent=""; log.classList.remove("hidden");
    const status = {}; steps.forEach(k=>status[k]="pending");
    const render = () => prog.innerHTML = `<div class="steps">${steps.map(k=>`
      <div class="srow ${status[k].startsWith('done')?'done':status[k]}">
        <span class="dot"></span><span class="sl">${labels[k]}</span>
        <span class="ss muted">${status[k].startsWith('done:')?status[k].slice(5):(status[k]==='running'?'…':'')}</span></div>`).join("")}</div>`;
    render();
    const es = new EventSource(`/api/update/stream?steps=${steps.join(",")}`);
    es.onmessage = (ev) => {
      const line = ev.data;
      if(line.startsWith("::step::")){ status[line.slice(8)]="running"; render(); }
      else if(line.startsWith("::done::")){ const [,k,sum]=line.split("::").filter(Boolean); status[k]="done:"+sum; render(); }
      else if(line.startsWith("::complete::")){ /* all steps done */ }
      else if(line.startsWith("::exit::")){
        es.close();
        document.querySelectorAll("#uall,#urun").forEach(b=>b.disabled=false);
        const ok = line.endsWith("0");
        prog.insertAdjacentHTML("beforeend", `<p class="${ok?'posv':'neg'}" style="margin-top:14px">${ok?'✓ Update complete.':'✗ Update failed — see log.'}</p>`);
        loaded.overview=false;  // refresh overview next time it's opened
        if(ok) setTimeout(draw, 600);
      } else if(line.trim()){ log.textContent += line+"\n"; log.scrollTop = log.scrollHeight; }
    };
    es.onerror = () => { es.close(); document.querySelectorAll("#uall,#urun").forEach(b=>b.disabled=false); };
  };

  draw();
};

show("overview");
