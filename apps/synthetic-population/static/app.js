// State
let currentView = "poll";
let selectedPollId = null;
let stats = {};
let pollTimers = {};
let populationSort = { col: null, dir: "asc" };

// API helper
async function api(path, opts = {}) {
    const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: resp.statusText }));
        throw new Error(err.error || resp.statusText);
    }
    return resp.json();
}

// Router
function navigate(view, data) {
    currentView = view;
    if (data) {
        if (data.pollId) selectedPollId = data.pollId;
    }
    document.querySelectorAll(".nav-link").forEach(el => {
        el.classList.toggle("active", el.dataset.view === view);
    });
    render();
}

// Main render
function render() {
    const app = document.getElementById("app");
    switch (currentView) {
        case "poll": renderPollView(app); break;
        case "results": renderResultsView(app); break;
        case "population": renderPopulationView(app); break;
        case "backtest": renderBacktestView(app); break;
        case "benchmark": renderBenchmarkView(app); break;
        case "events": renderEventsView(app); break;
        case "sources": renderSourcesView(app); break;
    }
}

// --- Helpers ---

function truncate(text, n) {
    if (!text) return "";
    return text.length > n ? text.slice(0, n) + "..." : text;
}

function snapshotBadge(snapshotId) {
    if (!snapshotId || snapshotId === "live") {
        return `<span class="badge badge-live">Live</span>`;
    }
    return `<span class="badge badge-backtest">Backtest</span>`;
}

function statusBadge(status) {
    if (status === "complete") return `<span class="badge badge-complete">Complete</span>`;
    return `<span class="badge badge-pending">${esc(status || "pending")}</span>`;
}

function pct(val) {
    if (val == null) return "0%";
    return (val * 100).toFixed(1) + "%";
}

function formatPollDate(dateStr) {
    if (!dateStr) return "";
    try {
        const d = new Date(dateStr);
        const month = (d.getMonth() + 1).toString().padStart(2, "0");
        const day = d.getDate().toString().padStart(2, "0");
        const hours = d.getHours();
        const mins = d.getMinutes().toString().padStart(2, "0");
        const ampm = hours >= 12 ? "pm" : "am";
        const h = hours % 12 || 12;
        return `${month}/${day} ${h}:${mins}${ampm}`;
    } catch { return dateStr.slice(0, 10); }
}

function extractName(profile) {
    if (profile.backstory) {
        const first = profile.backstory.split(/[\s,]/)[0];
        if (first && first.length > 1) return first;
    }
    return profile.profile_id || "Unknown";
}

// --- View 1: Poll ---

function renderPollView(el) {
    el.innerHTML = `
        <h2>Poll</h2>
        <div class="card">
            <div class="section-title">Ask a Question</div>
            <textarea id="poll-question" class="textarea" placeholder="Ask your population anything..."></textarea>
            <div id="poll-filter-toggle" style="margin-top:8px;cursor:pointer;font-size:12px;color:var(--accent);user-select:none">&#9654; Filter population</div>
            <div id="poll-filters" style="display:none;margin-top:8px;padding:10px 12px;background:var(--surface2);border-radius:6px">
                <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                    <select id="pf-state" class="select" style="max-width:130px"><option value="">All States</option></select>
                    <select id="pf-party" class="select" style="max-width:140px">
                        <option value="">All Parties</option>
                        <option value="dem">Democrats</option>
                        <option value="rep">Republicans</option>
                        <option value="independent">Independent</option>
                        <option value="strong_dem">Strong Dem</option>
                        <option value="lean_dem">Lean Dem</option>
                        <option value="strong_rep">Strong Rep</option>
                        <option value="lean_rep">Lean Rep</option>
                    </select>
                    <select id="pf-race" class="select" style="max-width:120px">
                        <option value="">All Races</option>
                        <option value="white">White</option>
                        <option value="black">Black</option>
                        <option value="hispanic">Hispanic</option>
                        <option value="asian">Asian</option>
                    </select>
                    <select id="pf-education" class="select" style="max-width:140px">
                        <option value="">All Education</option>
                        <option value="less_than_hs">Less than HS</option>
                        <option value="hs_diploma">HS Diploma</option>
                        <option value="some_college">Some College</option>
                        <option value="bachelors">Bachelors</option>
                        <option value="graduate">Graduate</option>
                    </select>
                    <select id="pf-age" class="select" style="max-width:110px">
                        <option value="">All Ages</option>
                        <option value="18-24">18-24</option>
                        <option value="25-34">25-34</option>
                        <option value="35-44">35-44</option>
                        <option value="45-54">45-54</option>
                        <option value="55-64">55-64</option>
                        <option value="65+">65+</option>
                    </select>
                </div>
                <div id="pf-match-count" style="font-size:11px;color:var(--text2);margin-top:6px"></div>
            </div>
            <div style="display:flex;gap:12px;align-items:center;margin-top:12px">
                <select id="poll-snapshot" class="select" style="max-width:250px">
                    <option value="live">Current Population (live)</option>
                </select>
                <button id="poll-run-btn" class="btn btn-primary">Run Poll</button>
            </div>
            <div id="poll-progress" class="progress-text" style="display:none"></div>
        </div>
        <div class="card">
            <div class="section-title">Recent Polls</div>
            <div id="poll-recent">Loading...</div>
        </div>
    `;

    // Load snapshots into dropdown
    api("/api/snapshots").then(snapshots => {
        const sel = document.getElementById("poll-snapshot");
        if (!sel) return;
        (snapshots || []).forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.snapshot_id;
            opt.textContent = `${s.label || s.snapshot_id} (${s.date || ""})`;
            sel.appendChild(opt);
        });
    }).catch(() => {});

    // Populate state dropdown from profiles
    api("/api/profiles").then(profiles => {
        const sel = document.getElementById("pf-state");
        if (!sel || !profiles) return;
        const states = [...new Set(profiles.map(p => p.state).filter(Boolean))].sort();
        states.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s;
            opt.textContent = s;
            sel.appendChild(opt);
        });
        // Store profiles for filter preview counts
        window._pollFilterProfiles = profiles;
    }).catch(() => {});

    // Filter toggle
    document.getElementById("poll-filter-toggle").addEventListener("click", () => {
        const panel = document.getElementById("poll-filters");
        const toggle = document.getElementById("poll-filter-toggle");
        const open = panel.style.display !== "none";
        panel.style.display = open ? "none" : "block";
        toggle.innerHTML = open ? "&#9654; Filter population" : "&#9660; Filter population";
    });

    // Filter change → update match count preview
    ["pf-state", "pf-party", "pf-race", "pf-education", "pf-age"].forEach(id => {
        document.getElementById(id)?.addEventListener("change", updatePollFilterCount);
    });

    // Load recent polls
    loadRecentPolls();

    // Run poll handler
    document.getElementById("poll-run-btn").addEventListener("click", async () => {
        const question = document.getElementById("poll-question").value.trim();
        if (!question) return;
        const snapshotVal = document.getElementById("poll-snapshot").value;
        const snapshotId = snapshotVal === "live" ? null : snapshotVal;
        const progress = document.getElementById("poll-progress");
        const btn = document.getElementById("poll-run-btn");

        // Collect active filters
        const filters = getPollFilters();

        btn.disabled = true;
        progress.style.display = "block";
        progress.textContent = "Creating poll...";

        try {
            const body = { question, snapshot_id: snapshotId || "live", filters };
            const result = await api("/api/polls", { method: "POST", body });
            const pollId = result.poll_id;
            const filterDesc = Object.entries(filters).filter(([,v]) => v).map(([k,v]) => `${k}=${v}`).join(", ");
            progress.innerHTML = `
                Poll created: <strong>${esc(pollId)}</strong> — ${result.archetype_count || "?"} archetypes, ${result.profile_count || "?"} profiles${filterDesc ? ` (filtered: ${esc(filterDesc)})` : ""}.<br>
                <span style="color:var(--text2)">Status: pending — prompts ready for Claude-in-Chrome automation.</span><br>
                <button class="btn btn-sm" style="margin-top:8px" id="view-poll-btn">View Poll</button>
            `;
            btn.disabled = false;
            document.getElementById("view-poll-btn")?.addEventListener("click", () => {
                navigate("results", { pollId });
            });
            loadRecentPolls();
        } catch (e) {
            if (e.message && e.message.includes("No CES survey data")) {
                progress.innerHTML = `<span style="color:var(--orange)">This question isn't covered by CES survey data.</span><br><span style="font-size:12px;color:var(--text2)">Covered topics: Trump/Congress approval, economy, immigration, healthcare, environment, taxes, minimum wage, student loans, spending cuts.</span>`;
            } else {
                progress.textContent = `Error: ${e.message}`;
            }
            btn.disabled = false;
        }
    });
}

function getPollFilters() {
    return {
        state: document.getElementById("pf-state")?.value || "",
        party_id: document.getElementById("pf-party")?.value || "",
        race: document.getElementById("pf-race")?.value || "",
        education: document.getElementById("pf-education")?.value || "",
        age_bracket: document.getElementById("pf-age")?.value || "",
    };
}

function updatePollFilterCount() {
    const countEl = document.getElementById("pf-match-count");
    if (!countEl) return;
    const profiles = window._pollFilterProfiles || [];
    const f = getPollFilters();
    const hasFilter = Object.values(f).some(v => v);
    if (!hasFilter) {
        countEl.textContent = "";
        return;
    }
    let matched = profiles;
    if (f.state) matched = matched.filter(p => p.state === f.state);
    if (f.race) matched = matched.filter(p => p.race === f.race);
    if (f.education) matched = matched.filter(p => p.education === f.education);
    if (f.age_bracket) matched = matched.filter(p => p.age_bracket === f.age_bracket);
    if (f.party_id) {
        if (f.party_id === "dem") matched = matched.filter(p => ["strong_dem", "dem", "lean_dem"].includes(p.party_id));
        else if (f.party_id === "rep") matched = matched.filter(p => ["strong_rep", "rep", "lean_rep"].includes(p.party_id));
        else matched = matched.filter(p => p.party_id === f.party_id);
    }
    const color = matched.length === 0 ? "var(--red)" : "var(--text2)";
    countEl.innerHTML = `<span style="color:${color}"><strong>${matched.length}</strong> of ${profiles.length} profiles match</span>`;
}

async function loadRecentPolls() {
    const container = document.getElementById("poll-recent");
    if (!container) return;
    try {
        const polls = await api("/api/polls");
        const recent = (polls || []).reverse().slice(0, 10);
        if (recent.length === 0) {
            container.innerHTML = '<p style="color:var(--text2);font-size:13px">No polls yet. Ask your first question above.</p>';
            return;
        }
        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Question</th>
                        <th>Date</th>
                        <th>Status</th>
                        <th style="text-align:center">Yes</th>
                        <th style="text-align:center">No</th>
                        <th style="text-align:center">Unsure</th>
                        <th style="width:32px"></th>
                        <th style="width:32px"></th>
                    </tr>
                </thead>
                <tbody>
                    ${recent.map(p => {
                        const d = p.distribution || {};
                        const hasResults = d.yes != null;
                        const fBadges = Object.entries(p.filters || {}).filter(([,v]) => v).map(([k,v]) => `<span class="filter-badge">${esc(v)}</span>`).join("");
                        return `
                        <tr data-poll-id="${esc(String(p.poll_id))}" style="cursor:pointer">
                            <td>${esc(truncate(p.question, 50))}${fBadges ? " " + fBadges : ""}</td>
                            <td style="white-space:nowrap">${esc(formatPollDate(p.date))}</td>
                            <td>${statusBadge(p.status)}</td>
                            <td style="text-align:center;font-weight:600;color:var(--green)">${hasResults ? pct(d.yes) : "--"}</td>
                            <td style="text-align:center;font-weight:600;color:var(--red)">${hasResults ? pct(d.no) : "--"}</td>
                            <td style="text-align:center;color:var(--text2)">${hasResults ? pct(d.unsure || 0) : "--"}</td>
                            <td style="text-align:center"><button class="poll-rerun-btn" data-rerun-question="${esc(p.question)}" data-rerun-filters='${JSON.stringify(p.filters || {}).replace(/'/g, "&#39;")}' title="Rerun with current population" style="background:none;border:none;cursor:pointer;color:var(--accent);font-size:14px;padding:2px 6px;border-radius:4px">&#8635;</button></td>
                            <td style="text-align:center"><button class="poll-delete-btn" data-delete-id="${esc(String(p.poll_id))}" title="Delete poll" style="background:none;border:none;cursor:pointer;color:var(--text2);font-size:16px;padding:2px 6px;border-radius:4px">&times;</button></td>
                        </tr>`;
                    }).join("")}
                </tbody>
            </table>
        `;
        container.querySelectorAll("tr[data-poll-id]").forEach(row => {
            row.addEventListener("click", (e) => {
                if (e.target.closest(".poll-delete-btn") || e.target.closest(".poll-rerun-btn")) return;
                navigate("results", { pollId: row.dataset.pollId });
            });
        });
        container.querySelectorAll(".poll-rerun-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const question = btn.dataset.rerunQuestion;
                const filters = JSON.parse(btn.dataset.rerunFilters || "{}");
                btn.disabled = true;
                btn.textContent = "...";
                try {
                    const created = await api("/api/polls", { method: "POST", body: { question, snapshot_id: "live", filters } });
                    await api(`/api/polls/${created.poll_id}/auto-complete`, { method: "POST" });
                    loadRecentPolls();
                    loadStats();
                    navigate("results", { pollId: created.poll_id });
                } catch (err) {
                    console.error("Rerun failed:", err);
                    btn.textContent = "\u21BB";
                    btn.disabled = false;
                }
            });
        });
        container.querySelectorAll(".poll-delete-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = btn.dataset.deleteId;
                try {
                    await api(`/api/polls/${id}`, { method: "DELETE" });
                    loadRecentPolls();
                    loadStats();
                } catch (err) {
                    console.error("Delete failed:", err);
                }
            });
        });
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load polls: ${esc(e.message)}</p>`;
    }
}

// --- View 2: Results ---

function renderResultsView(el) {
    if (!selectedPollId) {
        el.innerHTML = '<h2>Results</h2><p style="color:var(--text2)">Select a poll to view results.</p>';
        return;
    }
    el.innerHTML = '<h2>Results</h2><div id="results-content"><p style="color:var(--text2)">Loading...</p></div>';
    loadPollResults();
}

async function loadPollResults() {
    const container = document.getElementById("results-content");
    if (!container) return;

    try {
        const poll = await api(`/api/polls/${selectedPollId}`);

        // If pending or awaiting claude — show guided flow
        if (poll.status === "pending" || poll.status === "awaiting_claude") {
            await renderPendingPoll(container, poll);
            return;
        }

        const dist = poll.distribution || {};
        const yesVal = dist.yes || 0;
        const noVal = dist.no || 0;
        const unsureVal = dist.unsure || 0;
        const ci = poll.ci || {};
        const breakdowns = poll.breakdowns || {};
        const confidence = poll.mean_confidence;

        let html = `
            <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start">
                    <h3 style="margin:0 0 8px">${esc(poll.question || "")}</h3>
                    <button class="btn btn-sm" id="delete-poll-btn" title="Delete poll" style="color:var(--red);border-color:var(--red);flex-shrink:0">&#x2715;</button>
                </div>
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">
                    <span style="color:var(--text2);font-size:13px">${esc(poll.date || "")}</span>
                    ${snapshotBadge(poll.snapshot_id)}
                </div>
                <div class="section-title">Headline</div>
                <div style="display:flex;gap:24px;margin-bottom:16px;flex-wrap:wrap">
                    <div style="text-align:center">
                        <div style="font-size:32px;font-weight:700;color:var(--green)">${pct(yesVal)}</div>
                        <div style="font-size:12px;color:var(--text2)">Yes</div>
                        ${ci.yes ? `<div style="font-size:11px;color:var(--text2)">${pct(ci.yes[0])} - ${pct(ci.yes[1])}</div>` : ""}
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:32px;font-weight:700;color:var(--red)">${pct(noVal)}</div>
                        <div style="font-size:12px;color:var(--text2)">No</div>
                        ${ci.no ? `<div style="font-size:11px;color:var(--text2)">${pct(ci.no[0])} - ${pct(ci.no[1])}</div>` : ""}
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:32px;font-weight:700;color:var(--text2)">${pct(unsureVal)}</div>
                        <div style="font-size:12px;color:var(--text2)">Unsure</div>
                        ${ci.unsure ? `<div style="font-size:11px;color:var(--text2)">${pct(ci.unsure[0])} - ${pct(ci.unsure[1])}</div>` : ""}
                    </div>
                </div>
                ${confidence != null ? `<div style="font-size:13px;color:var(--text2);margin-bottom:16px">Mean confidence: <strong style="color:var(--text)">${Number(confidence).toFixed(1)}</strong> / 10</div>` : ""}
            </div>
        `;

        // Demographic breakdowns
        const breakdownKeys = Object.keys(breakdowns);
        if (breakdownKeys.length > 0) {
            html += `<div class="card"><div class="section-title">Demographic Breakdowns</div>`;
            for (const key of breakdownKeys) {
                const groups = breakdowns[key];
                html += `
                    <details style="margin-bottom:12px">
                        <summary style="cursor:pointer;font-weight:600;font-size:13px;color:var(--text);padding:4px 0">${esc(key)}</summary>
                        <div style="padding:8px 0">
                `;
                for (const [val, data] of Object.entries(groups || {})) {
                    const bYes = (data.yes || 0) * 100;
                    const bNo = (data.no || 0) * 100;
                    const bUnsure = (data.unsure || 0) * 100;
                    html += `
                        <div style="margin-bottom:8px">
                            <div style="font-size:12px;color:var(--text2);margin-bottom:2px">${esc(val)}</div>
                            <div style="display:flex;height:20px;border-radius:4px;overflow:hidden;background:var(--surface2)">
                                <div style="width:${bYes}%;background:var(--green);display:flex;align-items:center;justify-content:center;font-size:10px;color:#000;font-weight:600">${bYes > 5 ? bYes.toFixed(0) + "%" : ""}</div>
                                <div style="width:${bNo}%;background:var(--red);display:flex;align-items:center;justify-content:center;font-size:10px;color:#fff;font-weight:600">${bNo > 5 ? bNo.toFixed(0) + "%" : ""}</div>
                                <div style="width:${bUnsure}%;background:var(--border);display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--text2);font-weight:600">${bUnsure > 5 ? bUnsure.toFixed(0) + "%" : ""}</div>
                            </div>
                        </div>
                    `;
                }
                html += `</div></details>`;
            }
            html += `</div>`;
        }

        // Time series: find polls with same question
        try {
            const allPolls = await api("/api/polls");
            const related = (allPolls || []).filter(p => p.question === poll.question && p.status === "complete");
            if (related.length > 1) {
                html += `
                    <div class="card">
                        <div class="section-title">Time Series (same question)</div>
                        <table class="data-table">
                            <thead><tr><th>Date</th><th>Snapshot</th><th class="num">Yes</th><th class="num">No</th></tr></thead>
                            <tbody>
                                ${related.map(r => `
                                    <tr style="cursor:pointer" data-ts-poll="${esc(String(r.poll_id))}">
                                        <td>${esc(r.date || "")}</td>
                                        <td>${snapshotBadge(r.snapshot_id)}</td>
                                        <td class="num">${esc(r.headline_result || "--")}</td>
                                        <td class="num">--</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>
                `;
            }
        } catch (e) { /* ignore time series errors */ }

        // Raw responses (collapsible)
        if (poll.responses && poll.responses.length > 0) {
            html += `
                <div class="card">
                    <details>
                        <summary style="cursor:pointer;font-weight:600;font-size:13px;color:var(--text);padding:4px 0">Raw Responses (${poll.responses.length})</summary>
                        <table class="data-table" style="margin-top:8px">
                            <thead><tr><th>Archetype</th><th>Opinion</th><th class="num">Confidence</th><th class="num">Hedge</th></tr></thead>
                            <tbody>
                                ${poll.responses.map(r => `
                                    <tr>
                                        <td>${esc(String(r.archetype_id || ""))}</td>
                                        <td>${esc(r.opinion || "")}</td>
                                        <td class="num">${r.confidence != null ? r.confidence : "--"}</td>
                                        <td class="num">${r.hedge_score != null ? Number(r.hedge_score).toFixed(2) : "--"}</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </details>
                </div>
            `;
        }

        container.innerHTML = html;

        // Wire time series row clicks
        container.querySelectorAll("tr[data-ts-poll]").forEach(row => {
            row.addEventListener("click", () => {
                navigate("results", { pollId: row.dataset.tsPoll });
            });
        });

        // Wire delete button
        document.getElementById("delete-poll-btn")?.addEventListener("click", async () => {
            if (!confirm("Delete this poll?")) return;
            try {
                await api(`/api/polls/${selectedPollId}`, { method: "DELETE" });
                selectedPollId = null;
                loadStats();
                navigate("poll");
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        });
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load results: ${esc(e.message)}</p>`;
    }
}

async function renderPendingPoll(container, poll) {
    let prompts = [];
    try {
        prompts = await api(`/api/polls/${poll.poll_id}/prompts`);
    } catch (e) { /* no prompts */ }

    // Get latest state
    let detail = poll;
    try {
        detail = await api(`/api/polls/${poll.poll_id}`);
    } catch (e) {}

    const total = detail.archetype_count || prompts.length;
    const recorded = detail.responses_recorded || 0;
    const pctDone = total > 0 ? Math.round(recorded / total * 100) : 0;
    const status = detail.status || "pending";
    const isAwaiting = status === "awaiting_claude";
    const allDone = recorded >= total && total > 0;

    // Step indicator
    const step1Done = true; // poll created
    const step2Done = isAwaiting || allDone;
    const step3Done = allDone;

    let html = `
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <h3 style="margin:0 0 8px">${esc(detail.question || "")}</h3>
                <button class="btn btn-sm" id="delete-pending-poll-btn" title="Delete poll" style="color:var(--red);border-color:var(--red);flex-shrink:0">&#x2715;</button>
            </div>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">
                <span style="color:var(--text2);font-size:13px">${esc(detail.created_at || "")}</span>
                ${snapshotBadge(detail.snapshot_id)}
            </div>

            <!-- 3-step guided flow -->
            <div style="display:flex;gap:0;margin-bottom:20px">
                <div style="flex:1;text-align:center;padding:12px 8px;border-radius:8px 0 0 8px;background:${step1Done ? 'var(--green)' : 'var(--surface2)'};color:${step1Done ? '#000' : 'var(--text2)'}">
                    <div style="font-size:18px;font-weight:700">1</div>
                    <div style="font-size:11px;font-weight:600">Poll Created</div>
                    <div style="font-size:10px">${total} archetypes</div>
                </div>
                <div style="flex:1;text-align:center;padding:12px 8px;background:${step2Done ? 'var(--green)' : isAwaiting ? 'var(--accent)' : 'var(--surface2)'};color:${step2Done || isAwaiting ? '#000' : 'var(--text2)'}">
                    <div style="font-size:18px;font-weight:700">2</div>
                    <div style="font-size:11px;font-weight:600">${isAwaiting && !allDone ? 'Claude Working...' : allDone ? 'Responses In' : 'Send to Claude'}</div>
                    <div style="font-size:10px">${recorded}/${total} responses</div>
                </div>
                <div style="flex:1;text-align:center;padding:12px 8px;border-radius:0 8px 8px 0;background:${step3Done ? 'var(--green)' : 'var(--surface2)'};color:${step3Done ? '#000' : 'var(--text2)'}">
                    <div style="font-size:18px;font-weight:700">3</div>
                    <div style="font-size:11px;font-weight:600">View Results</div>
                    <div style="font-size:10px">${allDone ? 'Ready!' : 'Waiting...'}</div>
                </div>
            </div>

            <!-- Progress bar -->
            ${isAwaiting || recorded > 0 ? `
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
                    <div style="flex:1;height:10px;background:var(--surface2);border-radius:5px;overflow:hidden">
                        <div id="progress-fill" style="height:100%;width:${pctDone}%;background:${allDone ? 'var(--green)' : 'var(--accent)'};border-radius:5px;transition:width 0.3s"></div>
                    </div>
                    <span id="progress-label" style="font-size:13px;font-weight:600;color:var(--text);min-width:80px">${recorded} / ${total}</span>
                </div>
            ` : ''}
        </div>
    `;

    // Step 2: Send to Claude (if not yet sent)
    if (!isAwaiting && !allDone) {
        html += `
            <div class="card" style="border-color:var(--accent)">
                <div style="font-size:13px;color:var(--accent);font-weight:600;margin-bottom:8px">&#x2192; Next: Send to Claude</div>
                <p style="font-size:12px;color:var(--text2);margin-bottom:12px">
                    This will queue the poll for processing. Claude Code must be running to execute it.
                </p>
                <button id="send-to-claude-btn" class="btn btn-primary" style="width:100%">Send to Claude Queue</button>
            </div>
        `;
    }

    // Awaiting Claude: show instructions
    if (isAwaiting && !allDone) {
        html += `
            <div class="card" style="border-color:var(--orange)">
                <div style="font-size:13px;color:var(--orange);font-weight:600;margin-bottom:8px">&#x23F3; Waiting for Claude Code</div>
                <p style="font-size:12px;color:var(--text);margin-bottom:12px">
                    This poll is queued. Claude Code needs to process it.
                </p>
                <div style="background:var(--surface2);border-radius:6px;padding:16px;margin-bottom:12px">
                    <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Instructions</div>
                    <div style="font-size:13px;color:var(--text);margin-bottom:8px"><strong>1.</strong> Open a terminal in:</div>
                    <code style="display:block;background:var(--bg);padding:8px 12px;border-radius:4px;font-size:12px;color:var(--accent);margin-bottom:12px;word-break:break-all">C:\\Users\\slims\\Desktop\\Claude 2.0\\apps\\synthetic-population</code>
                    <div style="font-size:13px;color:var(--text);margin-bottom:8px"><strong>2.</strong> Launch Claude Code:</div>
                    <code style="display:block;background:var(--bg);padding:8px 12px;border-radius:4px;font-size:12px;color:var(--accent);margin-bottom:12px">claude</code>
                    <div style="font-size:13px;color:var(--text);margin-bottom:8px"><strong>3.</strong> Tell Claude:</div>
                    <code style="display:block;background:var(--bg);padding:8px 12px;border-radius:4px;font-size:12px;color:var(--accent)">run polls</code>
                </div>
                <p style="font-size:11px;color:var(--text2)">
                    The progress bar above will update automatically as Claude processes each archetype.
                </p>
            </div>
        `;
    }

    // Step 3: View Results (if all done)
    if (allDone) {
        html += `
            <div class="card" style="border-color:var(--green)">
                <div style="font-size:13px;color:var(--green);font-weight:600;margin-bottom:8px">&#x2192; Next: View Results</div>
                <p style="font-size:12px;color:var(--text2);margin-bottom:12px">
                    All ${total} archetype responses recorded. Click below to aggregate and see the breakdown.
                </p>
                <button id="view-results-btn" class="btn btn-primary" style="width:100%">Aggregate &amp; View Results</button>
                <div id="agg-status" class="progress-text" style="display:none"></div>
            </div>
        `;
    }

    // Prompts list (collapsible)
    if (prompts.length > 0) {
        html += `
            <div class="card">
                <details>
                    <summary style="cursor:pointer;font-weight:600;font-size:13px">View Prompts (${prompts.length})</summary>
                    <div style="margin-top:12px">
                        ${prompts.map(p => `
                            <details style="margin-bottom:8px">
                                <summary style="cursor:pointer;font-size:12px;color:var(--text2)">${esc(p.archetype_id)} (weight: ${(p.weight * 100).toFixed(1)}%)</summary>
                                <pre style="font-size:11px;color:var(--text);white-space:pre-wrap;padding:12px;background:var(--surface2);border-radius:6px;margin-top:4px;max-height:300px;overflow-y:auto">${esc(p.prompt_text)}</pre>
                            </details>
                        `).join("")}
                    </div>
                </details>
            </div>
        `;
    }

    container.innerHTML = html;

    // Wire: Send to Claude
    document.getElementById("send-to-claude-btn")?.addEventListener("click", async () => {
        try {
            await api(`/api/polls/${poll.poll_id}/send-to-claude`, { method: "POST" });
            renderPendingPoll(container, poll); // re-render with new state
        } catch (e) {
            alert(`Error: ${e.message}`);
        }
    });

    // Wire: View Results (aggregate first)
    document.getElementById("view-results-btn")?.addEventListener("click", async () => {
        const status = document.getElementById("agg-status");
        if (status) { status.style.display = "block"; status.textContent = "Aggregating..."; }
        try {
            await api(`/api/polls/${poll.poll_id}/aggregate`, { method: "POST" });
            loadStats();
            navigate("results", { pollId: poll.poll_id });
        } catch (e) {
            if (status) { status.textContent = `Error: ${e.message}`; status.style.color = "var(--red)"; }
        }
    });

    // Wire: Delete
    document.getElementById("delete-pending-poll-btn")?.addEventListener("click", async () => {
        if (!confirm("Delete this poll?")) return;
        try {
            await api(`/api/polls/${poll.poll_id}`, { method: "DELETE" });
            selectedPollId = null;
            loadStats();
            navigate("poll");
        } catch (e) {
            alert(`Error: ${e.message}`);
        }
    });

    // Auto-refresh progress if awaiting Claude
    if (isAwaiting && !allDone) {
        const refreshTimer = setInterval(async () => {
            try {
                const updated = await api(`/api/polls/${poll.poll_id}`);
                const newRecorded = updated.responses_recorded || 0;
                const newPct = total > 0 ? Math.round(newRecorded / total * 100) : 0;
                const fill = document.getElementById("progress-fill");
                const label = document.getElementById("progress-label");
                if (fill) fill.style.width = newPct + "%";
                if (label) label.textContent = `${newRecorded} / ${total}`;

                // If complete, re-render the whole thing
                if (newRecorded >= total || updated.status === "complete") {
                    clearInterval(refreshTimer);
                    renderPendingPoll(container, updated);
                }
            } catch (e) {
                clearInterval(refreshTimer);
            }
        }, 2000);
    }
}

// --- View 3: Population ---

let populationFilters = { search: "", sex: "", race: "", education: "", party_id: "", state: "" };
let populationData = [];

function renderPopulationView(el) {
    el.innerHTML = `
        <h2>Population</h2>
        <div class="filter-bar">
            <input id="pop-search" class="input" placeholder="Search..." value="${esc(populationFilters.search)}">
            <select id="pop-sex" class="select"><option value="">All Sex</option><option value="M">Male</option><option value="F">Female</option></select>
            <select id="pop-race" class="select"><option value="">All Race</option><option value="white">White</option><option value="black">Black</option><option value="hispanic">Hispanic</option><option value="asian">Asian</option><option value="other">Other</option></select>
            <select id="pop-education" class="select"><option value="">All Education</option><option value="less_than_hs">Less than HS</option><option value="hs_diploma">HS Diploma</option><option value="some_college">Some College</option><option value="bachelors">Bachelors</option><option value="graduate">Graduate</option></select>
            <select id="pop-party" class="select"><option value="">All Party</option><option value="strong_dem">Strong Dem</option><option value="dem">Democrat</option><option value="lean_dem">Lean Dem</option><option value="independent">Independent</option><option value="lean_rep">Lean Rep</option><option value="rep">Republican</option><option value="strong_rep">Strong Rep</option></select>
            <select id="pop-state" class="select"><option value="">All States</option></select>
        </div>
        <div class="quick-filters">
            <button class="quick-filter" data-qf="democrats">Democrats</button>
            <button class="quick-filter" data-qf="republicans">Republicans</button>
            <button class="quick-filter" data-qf="college">College+</button>
            <button class="quick-filter" data-qf="rural">Rural</button>
            <button class="quick-filter" data-qf="seniors">65+</button>
        </div>
        <div id="pop-table">Loading...</div>
        <div id="pop-detail" class="detail-panel">
            <button class="detail-panel-close" id="pop-detail-close">&times;</button>
            <div id="pop-detail-content"></div>
        </div>
    `;

    // Wire filter changes
    const filterIds = ["pop-search", "pop-sex", "pop-race", "pop-education", "pop-party", "pop-state"];
    const filterKeys = ["search", "sex", "race", "education", "party_id", "state"];
    filterIds.forEach((id, i) => {
        const el = document.getElementById(id);
        if (!el) return;
        const event = el.tagName === "INPUT" ? "input" : "change";
        el.addEventListener(event, () => {
            populationFilters[filterKeys[i]] = el.value;
            fetchPopulation();
        });
    });

    // Quick filters
    document.querySelectorAll(".quick-filter").forEach(btn => {
        btn.addEventListener("click", () => {
            const qf = btn.dataset.qf;
            // Reset filters first
            populationFilters = { search: "", sex: "", race: "", education: "", party_id: "", state: "", _quickFilter: qf };
            switch (qf) {
                case "democrats": populationFilters.party_id = "dem"; break;  // catches strong_dem, dem, lean_dem via startsWith
                case "republicans": populationFilters.party_id = "rep"; break;  // catches strong_rep, rep, lean_rep via startsWith
                case "college": populationFilters.education = "bachelors"; break;
                case "rural": populationFilters.search = "rural"; break;
                case "seniors": populationFilters.search = "65"; break;
            }
            // Update UI dropdowns
            document.getElementById("pop-search").value = populationFilters.search;
            document.getElementById("pop-sex").value = populationFilters.sex;
            document.getElementById("pop-race").value = populationFilters.race;
            document.getElementById("pop-education").value = populationFilters.education;
            document.getElementById("pop-party").value = populationFilters.party_id;
            document.getElementById("pop-state").value = populationFilters.state;
            // Toggle active class
            document.querySelectorAll(".quick-filter").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            fetchPopulation();
        });
    });

    // Detail panel close
    document.getElementById("pop-detail-close").addEventListener("click", () => {
        document.getElementById("pop-detail").classList.remove("open");
    });

    fetchPopulation();
}

async function fetchPopulation() {
    const container = document.getElementById("pop-table");
    if (!container) return;

    // For quick filters (democrats/republicans/college), use client-side filtering
    // since they need multi-value matching (e.g., strong_dem + dem + lean_dem)
    const qf = populationFilters._quickFilter;
    const params = new URLSearchParams();

    if (!qf || qf === "rural" || qf === "seniors") {
        // Use server-side filtering for exact matches and search
        if (populationFilters.search) params.set("search", populationFilters.search);
        if (populationFilters.sex) params.set("sex", populationFilters.sex);
        if (populationFilters.race) params.set("race", populationFilters.race);
        if (populationFilters.education && !qf) params.set("education", populationFilters.education);
        if (populationFilters.party_id && !qf) params.set("party_id", populationFilters.party_id);
        if (populationFilters.state) params.set("state", populationFilters.state);
    }

    try {
        let profiles = await api(`/api/profiles?${params.toString()}`);
        profiles = profiles || [];

        // Client-side quick filter for multi-value matches
        if (qf === "democrats") {
            profiles = profiles.filter(p => ["strong_dem", "dem", "lean_dem"].includes(p.party_id));
        } else if (qf === "republicans") {
            profiles = profiles.filter(p => ["strong_rep", "rep", "lean_rep"].includes(p.party_id));
        } else if (qf === "college") {
            profiles = profiles.filter(p => ["bachelors", "graduate"].includes(p.education));
        }

        populationData = profiles;
        renderPopulationTable();
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load profiles: ${esc(e.message)}</p>`;
    }
}

function buildColumnTooltips(data, cols) {
    const total = data.length;
    const tips = {};

    // Count values per column
    for (const col of cols) {
        const k = col.key;
        if (k === "name") {
            tips[k] = `<strong>${total}</strong> profiles shown`;
            continue;
        }

        const counts = {};
        for (const row of data) {
            const v = row[k] || "unknown";
            counts[v] = (counts[v] || 0) + 1;
        }

        // Columns with breakdown pivot tables
        const pivotCols = ["race", "party_id", "education", "sex", "age", "urban_rural"];
        if (pivotCols.includes(k)) {
            // For age, recount by age_bracket for a cleaner breakdown
            let pivotCounts = counts;
            if (k === "age") {
                pivotCounts = {};
                for (const row of data) {
                    const v = row["age_bracket"] || "unknown";
                    pivotCounts[v] = (pivotCounts[v] || 0) + 1;
                }
            }
            const sorted = Object.entries(pivotCounts).sort((a, b) => b[1] - a[1]);
            let html = `<strong>${total}</strong> profiles<table class="tooltip-pivot">`;
            for (const [val, count] of sorted) {
                const pctVal = ((count / total) * 100).toFixed(1);
                const barW = ((count / total) * 100).toFixed(0);
                html += `<tr><td class="tp-label">${esc(val)}</td><td class="tp-count">${count}</td><td class="tp-pct">${pctVal}%</td><td class="tp-bar"><div style="width:${barW}%"></div></td></tr>`;
            }
            html += `</table>`;
            tips[k] = html;
        } else {
            const unique = Object.keys(counts).length;
            tips[k] = `<strong>${total}</strong> profiles<br>${unique} unique values`;
        }
    }
    return tips;
}

function renderPopulationTable() {
    const container = document.getElementById("pop-table");
    if (!container) return;

    let data = [...populationData];

    // Sort
    if (populationSort.col) {
        data.sort((a, b) => {
            let aVal = a[populationSort.col] || "";
            let bVal = b[populationSort.col] || "";
            if (populationSort.col === "age") {
                aVal = Number(aVal) || 0;
                bVal = Number(bVal) || 0;
            }
            if (aVal < bVal) return populationSort.dir === "asc" ? -1 : 1;
            if (aVal > bVal) return populationSort.dir === "asc" ? 1 : -1;
            return 0;
        });
    }

    if (data.length === 0) {
        container.innerHTML = '<p style="color:var(--text2);font-size:13px">No profiles match your filters.</p>';
        return;
    }

    const cols = [
        { key: "name", label: "Name" },
        { key: "age", label: "Age" },
        { key: "sex", label: "Sex" },
        { key: "race", label: "Race" },
        { key: "education", label: "Education" },
        { key: "state", label: "State" },
        { key: "party_id", label: "Party" },
        { key: "archetype_id", label: "Archetype" },
    ];

    const arrow = (col) => {
        if (populationSort.col !== col) return "";
        return populationSort.dir === "asc" ? " &#9650;" : " &#9660;";
    };

    // Build column tooltips from current data
    const colTooltips = buildColumnTooltips(data, cols);

    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    ${cols.map(c => `<th data-sort="${c.key}" class="has-tooltip">${c.label}${arrow(c.key)}<div class="col-tooltip">${colTooltips[c.key] || ""}</div></th>`).join("")}
                </tr>
            </thead>
            <tbody>
                ${data.map(p => `
                    <tr data-profile-id="${esc(String(p.profile_id))}" style="cursor:pointer">
                        <td>${esc(extractName(p))}</td>
                        <td class="num">${p.age || ""}</td>
                        <td>${esc(p.sex || "")}</td>
                        <td>${esc(p.race || "")}</td>
                        <td>${esc(p.education || "")}</td>
                        <td>${esc(p.state || "")}</td>
                        <td>${esc(p.party_id || "")}</td>
                        <td>${esc(p.archetype_id || "")}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;

    // Sort handlers
    container.querySelectorAll("th[data-sort]").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (populationSort.col === col) {
                populationSort.dir = populationSort.dir === "asc" ? "desc" : "asc";
            } else {
                populationSort.col = col;
                populationSort.dir = "asc";
            }
            renderPopulationTable();
        });
    });

    // Row click → detail
    container.querySelectorAll("tr[data-profile-id]").forEach(row => {
        row.addEventListener("click", () => {
            loadProfileDetail(row.dataset.profileId);
        });
    });
}

async function loadProfileDetail(profileId) {
    const panel = document.getElementById("pop-detail");
    const content = document.getElementById("pop-detail-content");
    if (!panel || !content) return;

    content.innerHTML = '<p style="color:var(--text2)">Loading...</p>';
    panel.classList.add("open");

    try {
        const p = await api(`/api/profiles/${profileId}`);
        let html = `<h3 style="margin:0 0 16px">${esc(extractName(p))}</h3>`;

        if (p.backstory) {
            html += `
                <div class="card" style="font-style:italic;font-size:13px;line-height:1.6;color:var(--text2)">
                    ${esc(p.backstory)}
                </div>
            `;
        }

        // Group ALL fields by category
        const fieldCategories = {
            "Identity": ["profile_id", "archetype_id", "batch_id"],
            "Demographics": ["age", "age_bracket", "sex", "race", "education", "marital_status", "children_count", "citizenship", "veteran_status", "disability", "language", "household_size", "generation"],
            "Geography": ["state", "urban_rural", "region", "census_division", "metro_area", "county_type", "population_density", "cost_of_living_area", "time_zone", "climate_zone"],
            "Economics": ["income", "income_bracket", "employment_status", "occupation", "industry", "income_source", "hours_worked", "employer_size", "union_membership", "homeownership", "health_insurance", "commute_mode"],
            "Financial": ["risk_tolerance", "debt_level", "savings_months", "credit_score_bracket", "financial_literacy_score", "financial_sophistication", "tax_approach", "retirement_strategy", "uses_financial_advisor", "insurance_coverage"],
            "Political": ["party_id", "ideology", "vote_2020", "vote_2024", "registration_status", "political_interest", "partisan_strength", "swing_voter"],
            "Policy Positions": ["abortion", "gun_control", "immigration", "climate_policy", "healthcare_system", "government_spending", "trade_policy", "criminal_justice", "education_policy", "social_security", "marijuana", "minimum_wage", "foreign_policy", "tax_policy", "tech_regulation"],
            "Psychology": ["racial_resentment", "authoritarianism", "social_trust", "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism", "institutional_confidence", "meritocracy_belief"],
            "Religion": ["religion_affiliation", "religion_denomination", "religion_attendance", "religion_biblical_literalism", "religion_importance"],
            "Media": ["primary_news_source", "secondary_news_source", "social_media_primary", "social_media_news", "podcast_listener", "media_trust", "info_ecosystem", "news_frequency"],
            "Science/Health": ["vaccine_attitude", "climate_change_belief", "climate_policy_support", "evolution_belief", "trust_medical_establishment", "trust_scientific_establishment"],
        };

        const skip = new Set(["backstory", "drift_log", "created_at", "updated_at"]);
        const shown = new Set();

        for (const [category, fields] of Object.entries(fieldCategories)) {
            const present = fields.filter(f => p[f] != null && !skip.has(f));
            if (present.length === 0) continue;
            html += `<details ${category === "Demographics" || category === "Identity" ? "open" : ""}><summary style="cursor:pointer;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text2);padding:8px 0;font-weight:600">${esc(category)} (${present.length})</summary><div class="card" style="margin-bottom:8px">`;
            for (const key of present) {
                const val = p[key];
                const display = typeof val === "number" ? (Number.isInteger(val) ? String(val) : val.toFixed(3)) : String(val);
                html += `<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;border-bottom:1px solid var(--border)">
                    <span style="color:var(--text2)">${esc(key.replace(/_/g, " "))}</span>
                    <span style="color:var(--text);font-weight:500;text-align:right;max-width:60%">${esc(display)}</span>
                </div>`;
                shown.add(key);
            }
            html += `</div></details>`;
        }

        // Show any remaining fields not in categories (custom/namespaced)
        const remaining = Object.keys(p).filter(k => !shown.has(k) && !skip.has(k) && p[k] != null && !k.startsWith("_"));
        if (remaining.length > 0) {
            html += `<details><summary style="cursor:pointer;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text2);padding:8px 0;font-weight:600">Other (${remaining.length})</summary><div class="card" style="margin-bottom:8px">`;
            for (const key of remaining) {
                const val = p[key];
                const display = typeof val === "number" ? (Number.isInteger(val) ? String(val) : val.toFixed(3)) : String(val);
                html += `<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;border-bottom:1px solid var(--border)">
                    <span style="color:var(--text2)">${esc(key.replace(/_/g, " "))}</span>
                    <span style="color:var(--text);font-weight:500;text-align:right;max-width:60%">${esc(display)}</span>
                </div>`;
            }
            html += `</div></details>`;
        }

        // Drift log
        if (p.drift_log && p.drift_log.length > 0) {
            html += `<div class="section-title">Drift Log</div><div class="card">`;
            for (const entry of p.drift_log) {
                html += `
                    <div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:12px">
                        <span style="color:var(--text2)">${esc(entry.date || "")}</span>
                        <span style="margin-left:8px;color:var(--text)">${esc(entry.description || entry.change || JSON.stringify(entry))}</span>
                    </div>
                `;
            }
            html += `</div>`;
        }

        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = `<p style="color:var(--text2)">Failed to load profile: ${esc(e.message)}</p>`;
    }
}

// --- View 4: Backtest ---

function renderBacktestView(el) {
    const today = new Date().toISOString().split("T")[0];
    el.innerHTML = `
        <h2>Backtest</h2>
        <div class="card">
            <div class="section-title">Create Snapshot</div>
            <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Date</label>
                    <input id="snap-date" type="date" class="input" style="max-width:180px" value="${today}">
                </div>
                <div style="flex:1">
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Label</label>
                    <input id="snap-label" class="input" placeholder="e.g. Pre-election baseline">
                </div>
                <button id="snap-save-btn" class="btn btn-primary">Save Snapshot</button>
            </div>
            <div id="snap-status" class="progress-text" style="display:none"></div>
        </div>
        <div class="card">
            <div class="section-title">Snapshots</div>
            <div id="snap-list">Loading...</div>
        </div>
        <div class="card">
            <div class="section-title">Compare Snapshots</div>
            <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Snapshot A</label>
                    <select id="compare-a" class="select" style="max-width:220px"><option value="live">Live</option></select>
                </div>
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Snapshot B</label>
                    <select id="compare-b" class="select" style="max-width:220px"><option value="live">Live</option></select>
                </div>
                <div style="flex:1">
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Question</label>
                    <input id="compare-question" class="input" placeholder="Question to compare across snapshots">
                </div>
                <button id="compare-btn" class="btn btn-primary">Compare</button>
            </div>
            <div id="compare-status" class="progress-text" style="display:none"></div>
        </div>
    `;

    loadSnapshotList();

    // Save snapshot
    document.getElementById("snap-save-btn").addEventListener("click", async () => {
        const date = document.getElementById("snap-date").value;
        const label = document.getElementById("snap-label").value.trim();
        const status = document.getElementById("snap-status");
        if (!date) return;

        status.style.display = "block";
        status.textContent = "Creating snapshot...";
        try {
            await api("/api/snapshots", { method: "POST", body: { date, label: label || `Snapshot ${date}` } });
            status.textContent = "Snapshot created.";
            document.getElementById("snap-label").value = "";
            loadSnapshotList();
            setTimeout(() => { if (status) status.style.display = "none"; }, 2000);
        } catch (e) {
            status.textContent = `Error: ${e.message}`;
        }
    });

    // Compare
    document.getElementById("compare-btn").addEventListener("click", async () => {
        const a = document.getElementById("compare-a").value;
        const b = document.getElementById("compare-b").value;
        const question = document.getElementById("compare-question").value.trim();
        const status = document.getElementById("compare-status");
        if (!question) return;

        status.style.display = "block";
        status.textContent = "Creating comparison polls...";
        try {
            const bodyA = { question };
            if (a !== "live") bodyA.snapshot_id = a;
            const bodyB = { question };
            if (b !== "live") bodyB.snapshot_id = b;
            const [pollA, pollB] = await Promise.all([
                api("/api/polls", { method: "POST", body: bodyA }),
                api("/api/polls", { method: "POST", body: bodyB }),
            ]);
            status.textContent = `Polls created (${pollA.poll_id}, ${pollB.poll_id}). Navigate to Results to view.`;
            navigate("results", { pollId: pollA.poll_id });
        } catch (e) {
            status.textContent = `Error: ${e.message}`;
        }
    });
}

async function loadSnapshotList() {
    const container = document.getElementById("snap-list");
    if (!container) return;

    try {
        const snapshots = await api("/api/snapshots");
        if (!snapshots || snapshots.length === 0) {
            container.innerHTML = '<p style="color:var(--text2);font-size:13px">No snapshots yet.</p>';
            updateSnapshotDropdowns([]);
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead><tr><th>Date</th><th>Label</th><th class="num">Profiles</th><th>Events Through</th><th></th></tr></thead>
                <tbody>
                    ${snapshots.map(s => `
                        <tr>
                            <td>${esc(s.date || "")}</td>
                            <td>${esc(s.label || "")}</td>
                            <td class="num">${s.profile_count || 0}</td>
                            <td>${esc(s.events_applied_through || "--")}</td>
                            <td><button class="btn btn-sm" data-delete-snap="${esc(String(s.snapshot_id))}">Delete</button></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `;

        // Delete handlers
        container.querySelectorAll("button[data-delete-snap]").forEach(btn => {
            btn.addEventListener("click", async () => {
                if (!confirm("Delete this snapshot?")) return;
                try {
                    await api(`/api/snapshots/${btn.dataset.deleteSnap}`, { method: "DELETE" });
                    loadSnapshotList();
                } catch (e) {
                    alert(`Error: ${e.message}`);
                }
            });
        });

        updateSnapshotDropdowns(snapshots);
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load snapshots: ${esc(e.message)}</p>`;
    }
}

function updateSnapshotDropdowns(snapshots) {
    ["compare-a", "compare-b"].forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="live">Live</option>';
        (snapshots || []).forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.snapshot_id;
            opt.textContent = `${s.label || s.snapshot_id} (${s.date || ""})`;
            sel.appendChild(opt);
        });
        sel.value = current || "live";
    });
}

// --- View: Benchmark ---

function renderBenchmarkView(el) {
    el.innerHTML = `
        <h2>Benchmark</h2>
        <p style="font-size:13px;color:var(--text2);margin-bottom:16px">Compare your synthetic population against real polls. Click "Run" to test any question, or "Run All" to benchmark everything.</p>
        <div style="display:flex;gap:8px;margin-bottom:16px">
            <button id="bm-run-all" class="btn btn-primary">Run All Benchmarks</button>
            <span id="bm-status" style="font-size:12px;color:var(--text2);align-self:center"></span>
        </div>
        <div id="bm-summary" style="margin-bottom:16px"></div>
        <div id="bm-list">Loading...</div>
        <div class="card" style="margin-top:16px">
            <div class="section-title">Custom Comparison</div>
            <p style="font-size:12px;color:var(--text2);margin-bottom:8px">Enter a real poll result to compare against your population.</p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
                <div style="flex:1;min-width:200px">
                    <label style="font-size:11px;color:var(--text2);display:block;margin-bottom:4px">Question</label>
                    <input id="bm-custom-q" class="input" placeholder="e.g. Do you approve of...">
                </div>
                <div style="width:80px">
                    <label style="font-size:11px;color:var(--text2);display:block;margin-bottom:4px">Real Yes%</label>
                    <input id="bm-custom-yes" class="input" type="number" min="0" max="100" placeholder="47">
                </div>
                <div style="width:80px">
                    <label style="font-size:11px;color:var(--text2);display:block;margin-bottom:4px">Real No%</label>
                    <input id="bm-custom-no" class="input" type="number" min="0" max="100" placeholder="49">
                </div>
                <div style="width:100px">
                    <label style="font-size:11px;color:var(--text2);display:block;margin-bottom:4px">Source</label>
                    <input id="bm-custom-src" class="input" placeholder="Gallup">
                </div>
                <button id="bm-custom-run" class="btn btn-primary">Compare</button>
            </div>
            <div id="bm-custom-result" style="margin-top:8px"></div>
        </div>
    `;

    loadBenchmarks();

    document.getElementById("bm-run-all").addEventListener("click", runAllBenchmarks);

    document.getElementById("bm-custom-run").addEventListener("click", async () => {
        const q = document.getElementById("bm-custom-q").value.trim();
        const yesVal = parseFloat(document.getElementById("bm-custom-yes").value);
        const noVal = parseFloat(document.getElementById("bm-custom-no").value);
        const src = document.getElementById("bm-custom-src").value.trim();
        if (!q || isNaN(yesVal) || isNaN(noVal)) return;
        const unsureVal = Math.max(0, 100 - yesVal - noVal);
        const resultEl = document.getElementById("bm-custom-result");
        resultEl.innerHTML = '<span style="color:var(--text2)">Running comparison...</span>';
        try {
            const cmp = await api("/api/benchmarks/compare", { method: "POST", body: {
                question: q,
                real_results: { yes: yesVal / 100, no: noVal / 100, unsure: unsureVal / 100 },
                source: src,
                runs: 10,
            }});
            resultEl.innerHTML = renderComparisonInline(cmp);
            loadBenchmarks();
        } catch (e) {
            resultEl.innerHTML = `<span style="color:var(--red)">Error: ${esc(e.message)}</span>`;
        }
    });
}

function renderComparisonInline(cmp) {
    const r = cmp.real, s = cmp.synthetic, e = cmp.errors;
    const errColor = v => Math.abs(v) <= 0.03 ? "var(--green)" : Math.abs(v) <= 0.08 ? "var(--orange)" : "var(--red)";
    const fmtE = v => (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
    return `
        <div style="display:flex;gap:24px;font-size:13px;padding:8px 0">
            <div>Yes: <strong style="color:var(--green)">${pct(s.yes)}</strong> vs real ${pct(r.yes)} <span style="color:${errColor(e.yes)}">(${fmtE(e.yes)})</span></div>
            <div>No: <strong style="color:var(--red)">${pct(s.no)}</strong> vs real ${pct(r.no)} <span style="color:${errColor(e.no)}">(${fmtE(e.no)})</span></div>
            <div>Unsure: <strong>${pct(s.unsure)}</strong> vs real ${pct(r.unsure || 0)} <span style="color:${errColor(e.unsure)}">(${fmtE(e.unsure)})</span></div>
            <div>MAE: <strong style="color:${cmp.mae <= 0.05 ? "var(--green)" : cmp.mae <= 0.10 ? "var(--orange)" : "var(--red)"}">${(cmp.mae * 100).toFixed(1)}%</strong></div>
        </div>
    `;
}

async function loadBenchmarks() {
    const container = document.getElementById("bm-list");
    if (!container) return;
    try {
        const benchmarks = await api("/api/benchmarks");
        if (!benchmarks || benchmarks.length === 0) {
            container.innerHTML = '<p style="color:var(--text2)">No benchmarks loaded.</p>';
            return;
        }
        container.innerHTML = `
            <table class="data-table">
                <thead><tr>
                    <th>Question</th>
                    <th>Source</th>
                    <th style="text-align:center">Real Yes</th>
                    <th style="text-align:center">Real No</th>
                    <th style="text-align:center">Synth Yes</th>
                    <th style="text-align:center">Synth No</th>
                    <th style="text-align:center">Error</th>
                    <th style="width:60px"></th>
                </tr></thead>
                <tbody>
                    ${benchmarks.map((b, i) => {
                        const r = b.real_results || {};
                        const cmp = b.last_comparison || {};
                        const s = cmp.synthetic || {};
                        const hasSynth = s.yes != null;
                        const mae = cmp.mae;
                        const maeColor = mae != null ? (mae <= 0.05 ? "var(--green)" : mae <= 0.10 ? "var(--orange)" : "var(--red)") : "var(--text2)";
                        return `<tr>
                            <td style="max-width:280px">${esc(truncate(b.question, 55))}</td>
                            <td style="font-size:11px;color:var(--text2);white-space:nowrap">${esc(b.source || "")}</td>
                            <td style="text-align:center;font-weight:600;color:var(--green)">${pct(r.yes)}</td>
                            <td style="text-align:center;font-weight:600;color:var(--red)">${pct(r.no)}</td>
                            <td style="text-align:center;${hasSynth ? "font-weight:600;color:var(--green)" : "color:var(--text2)"}">${hasSynth ? pct(s.yes) : "--"}</td>
                            <td style="text-align:center;${hasSynth ? "font-weight:600;color:var(--red)" : "color:var(--text2)"}">${hasSynth ? pct(s.no) : "--"}</td>
                            <td style="text-align:center;font-weight:600;color:${maeColor}">${mae != null ? (mae * 100).toFixed(1) + "%" : "--"}</td>
                            <td><button class="btn btn-sm" data-bm-run="${i}" data-bm-q="${esc(b.question)}" data-bm-real='${JSON.stringify(r).replace(/'/g, "&#39;")}' data-bm-src="${esc(b.source || "")}" data-bm-date="${esc(b.date || "")}" data-bm-cat="${esc(b.category || "")}">Run</button></td>
                        </tr>`;
                    }).join("")}
                </tbody>
            </table>
        `;
        container.querySelectorAll("[data-bm-run]").forEach(btn => {
            btn.addEventListener("click", async () => {
                btn.disabled = true;
                btn.textContent = "...";
                try {
                    await api("/api/benchmarks/compare", { method: "POST", body: {
                        question: btn.dataset.bmQ,
                        real_results: JSON.parse(btn.dataset.bmReal),
                        source: btn.dataset.bmSrc,
                        date: btn.dataset.bmDate,
                        category: btn.dataset.bmCat,
                        runs: 10,
                    }});
                    loadBenchmarks();
                } catch (e) {
                    console.error("Benchmark run failed:", e);
                }
                btn.disabled = false;
                btn.textContent = "Run";
            });
        });
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load: ${esc(e.message)}</p>`;
    }
}

async function runAllBenchmarks() {
    const btn = document.getElementById("bm-run-all");
    const status = document.getElementById("bm-status");
    btn.disabled = true;
    try {
        const benchmarks = await api("/api/benchmarks");
        let done = 0;
        for (const b of benchmarks) {
            if (!b.real_results) continue;
            status.textContent = `Running ${++done} of ${benchmarks.length}...`;
            await api("/api/benchmarks/compare", { method: "POST", body: {
                question: b.question,
                real_results: b.real_results,
                source: b.source || "",
                date: b.date || "",
                category: b.category || "",
                runs: 10,
            }});
        }
        // Show summary
        const updated = await api("/api/benchmarks");
        const maes = updated.filter(b => b.last_comparison?.mae != null).map(b => b.last_comparison.mae);
        const avgMae = maes.length ? maes.reduce((a, b) => a + b, 0) / maes.length : 0;
        const summaryEl = document.getElementById("bm-summary");
        if (summaryEl && maes.length) {
            const color = avgMae <= 0.05 ? "var(--green)" : avgMae <= 0.10 ? "var(--orange)" : "var(--red)";
            summaryEl.innerHTML = `
                <div style="padding:12px 16px;background:var(--surface2);border-radius:6px;font-size:13px">
                    Avg error across <strong>${maes.length}</strong> benchmarks: <strong style="color:${color}">${(avgMae * 100).toFixed(1)}%</strong>
                    &nbsp;|&nbsp; Best: ${(Math.min(...maes) * 100).toFixed(1)}% &nbsp;|&nbsp; Worst: ${(Math.max(...maes) * 100).toFixed(1)}%
                </div>
            `;
        }
        status.textContent = `Done — ${done} benchmarks completed`;
        loadBenchmarks();
    } catch (e) {
        status.textContent = `Error: ${e.message}`;
    }
    btn.disabled = false;
}

// --- View 5: Events ---

function renderEventsView(el) {
    el.innerHTML = `
        <h2>Events</h2>
        <div class="card">
            <div class="section-title">World Context</div>
            <p style="font-size:12px;color:var(--text2);margin-bottom:8px">Fetch real headlines from public news feeds (AP, NPR, BBC, Reuters). The population absorbs this info and their poll responses shift accordingly.</p>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
                <button id="wu-fetch" class="btn btn-primary">Refresh World Context</button>
                <button id="wu-clear" class="btn btn-sm">Clear Auto</button>
                <span id="wu-status" style="font-size:12px;color:var(--text2)"></span>
            </div>
            <div id="wu-shifts" style="margin-bottom:8px"></div>
            <div id="wu-list"></div>
            <details style="margin-top:12px">
                <summary style="font-size:12px;color:var(--text2);cursor:pointer">Add manual update</summary>
                <div style="margin-top:8px">
                    <textarea id="wu-text" class="textarea" style="min-height:60px" placeholder="Paste any news or info..."></textarea>
                    <button id="wu-manual" class="btn btn-sm" style="margin-top:4px">Add</button>
                </div>
            </details>
        </div>
        <div class="card">
            <div class="section-title">Add Event</div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Date</label>
                    <input id="evt-date" type="date" class="input" style="max-width:180px" value="${new Date().toISOString().split("T")[0]}">
                </div>
                <div style="flex:1">
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Description</label>
                    <textarea id="evt-desc" class="textarea" style="min-height:50px" placeholder="Describe the event..."></textarea>
                </div>
            </div>
            <div class="section-title">Affected Segments</div>
            <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Variable</label>
                    <select id="evt-seg-var" class="select" style="max-width:150px">
                        <option value="party_id">party_id</option>
                        <option value="race">race</option>
                        <option value="education">education</option>
                        <option value="age_bracket">age_bracket</option>
                        <option value="sex">sex</option>
                        <option value="state">state</option>
                        <option value="urban_rural">urban_rural</option>
                        <option value="religion">religion</option>
                    </select>
                </div>
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Value</label>
                    <input id="evt-seg-val" class="input" style="max-width:150px" placeholder="e.g. democrat">
                </div>
                <div>
                    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Delta</label>
                    <input id="evt-seg-delta" class="input" style="max-width:100px" placeholder="e.g. +0.1">
                </div>
                <button id="evt-add-seg" class="btn btn-sm">+ Add Segment</button>
            </div>
            <div id="evt-segments" style="margin-bottom:12px"></div>
            <button id="evt-submit" class="btn btn-primary">Add Event</button>
            <div id="evt-status" class="progress-text" style="display:none"></div>
        </div>
        <div class="card">
            <div class="section-title">Event Log</div>
            <div id="evt-list">Loading...</div>
        </div>
    `;

    let segments = [];

    // Add segment
    document.getElementById("evt-add-seg").addEventListener("click", () => {
        const variable = document.getElementById("evt-seg-var").value;
        const value = document.getElementById("evt-seg-val").value.trim();
        const delta = document.getElementById("evt-seg-delta").value.trim();
        if (!value) return;
        segments.push({ variable, value, delta });
        renderSegmentList();
        document.getElementById("evt-seg-val").value = "";
        document.getElementById("evt-seg-delta").value = "";
    });

    function renderSegmentList() {
        const container = document.getElementById("evt-segments");
        if (!container) return;
        if (segments.length === 0) { container.innerHTML = ""; return; }
        container.innerHTML = segments.map((s, i) => `
            <span class="badge badge-live" style="margin-right:4px;cursor:pointer" data-remove-seg="${i}" title="Click to remove">
                ${esc(s.variable)}=${esc(s.value)} (${esc(s.delta || "0")}) &times;
            </span>
        `).join("");
        container.querySelectorAll("[data-remove-seg]").forEach(badge => {
            badge.addEventListener("click", () => {
                segments.splice(Number(badge.dataset.removeSeg), 1);
                renderSegmentList();
            });
        });
    }

    // Submit event
    document.getElementById("evt-submit").addEventListener("click", async () => {
        const date = document.getElementById("evt-date").value;
        const description = document.getElementById("evt-desc").value.trim();
        const status = document.getElementById("evt-status");
        if (!description) return;

        const affected_segments = segments.length > 0 ? segments : undefined;

        status.style.display = "block";
        status.textContent = "Creating event...";
        try {
            await api("/api/events", { method: "POST", body: { date, description, affected_segments } });
            status.textContent = "Event created.";
            document.getElementById("evt-desc").value = "";
            segments = [];
            renderSegmentList();
            loadEventList();
            setTimeout(() => { if (status) status.style.display = "none"; }, 2000);
        } catch (e) {
            status.textContent = `Error: ${e.message}`;
        }
    });

    // World Context handlers
    document.getElementById("wu-fetch").addEventListener("click", async () => {
        const btn = document.getElementById("wu-fetch");
        const status = document.getElementById("wu-status");
        btn.disabled = true;
        btn.textContent = "Fetching headlines...";
        status.textContent = "";
        try {
            const result = await api("/api/world-updates/fetch", { method: "POST" });
            status.innerHTML = `Scanned <strong>${result.headlines_scanned}</strong> headlines, ingested <strong>${result.fetched}</strong> updates`;
            loadWorldUpdates();
        } catch (e) {
            status.textContent = `Error: ${e.message}`;
        }
        btn.disabled = false;
        btn.textContent = "Refresh World Context";
    });
    document.getElementById("wu-clear").addEventListener("click", async () => {
        await api("/api/world-updates/clear-auto", { method: "POST" });
        loadWorldUpdates();
    });
    document.getElementById("wu-manual")?.addEventListener("click", async () => {
        const text = document.getElementById("wu-text").value.trim();
        if (!text) return;
        await api("/api/world-updates", { method: "POST", body: { text } });
        document.getElementById("wu-text").value = "";
        loadWorldUpdates();
    });
    loadWorldUpdates();

    loadEventList();
}

async function loadWorldUpdates() {
    const container = document.getElementById("wu-list");
    const shiftsEl = document.getElementById("wu-shifts");
    if (!container) return;
    try {
        const [updates, activeShifts] = await Promise.all([
            api("/api/world-updates"),
            api("/api/world-updates/active-shifts"),
        ]);

        // Show aggregate shift summary
        if (shiftsEl && activeShifts.active_count > 0) {
            const s = activeShifts.shifts;
            const fmtS = v => v > 0 ? `+${(v*100).toFixed(1)}%` : `${(v*100).toFixed(1)}%`;
            const colorS = v => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text2)";
            shiftsEl.innerHTML = `
                <div style="display:flex;gap:16px;font-size:13px;padding:8px 12px;background:var(--surface2);border-radius:6px">
                    <span style="color:var(--text2)">${activeShifts.active_count} active updates shifting polls:</span>
                    <span>Dem <strong style="color:${colorS(s.dem)}">${fmtS(s.dem)}</strong></span>
                    <span>Rep <strong style="color:${colorS(s.rep)}">${fmtS(s.rep)}</strong></span>
                    <span>Ind <strong style="color:${colorS(s.independent)}">${fmtS(s.independent)}</strong></span>
                </div>
            `;
        } else if (shiftsEl) {
            shiftsEl.innerHTML = "";
        }

        if (!updates || updates.length === 0) {
            container.innerHTML = '<p style="color:var(--text2);font-size:12px">No world context loaded. Click "Refresh World Context" to fetch current headlines.</p>';
            return;
        }
        container.innerHTML = `
            <table class="data-table">
                <thead><tr>
                    <th>Headline</th>
                    <th>Source</th>
                    <th>Topics</th>
                    <th>Dir</th>
                    <th style="text-align:center">Dem</th>
                    <th style="text-align:center">Rep</th>
                    <th style="text-align:center">Ind</th>
                    <th style="width:60px"></th>
                </tr></thead>
                <tbody>
                    ${updates.map(u => {
                        const s = u.shifts || {};
                        const fmtShift = v => v > 0 ? `<span style="color:var(--green)">+${(v*100).toFixed(1)}%</span>` : v < 0 ? `<span style="color:var(--red)">${(v*100).toFixed(1)}%</span>` : `<span style="color:var(--text2)">0</span>`;
                        const dirBadge = u.direction === "positive" ? "badge-complete" : u.direction === "negative" ? "badge-pending" : "badge-backtest";
                        const activeStyle = u.active === false ? "opacity:0.4" : "";
                        const srcLabel = u.feed || (u.source === "manual" ? "manual" : "");
                        return `<tr style="${activeStyle}">
                            <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(u.text)}${u.description ? "\n\n" + esc(u.description) : ""}">${esc(truncate(u.text, 55))}</td>
                            <td style="font-size:11px;color:var(--text2);white-space:nowrap">${esc(srcLabel)}</td>
                            <td>${(u.topics||[]).map(t => `<span class="badge badge-live" style="margin-right:2px">${esc(t)}</span>`).join("")}</td>
                            <td><span class="badge ${dirBadge}">${esc(u.direction)}</span></td>
                            <td style="text-align:center">${fmtShift(s.dem || 0)}</td>
                            <td style="text-align:center">${fmtShift(s.rep || 0)}</td>
                            <td style="text-align:center">${fmtShift(s.independent || 0)}</td>
                            <td style="white-space:nowrap">
                                <button class="btn btn-sm" data-toggle-wu="${esc(u.id)}" title="${u.active !== false ? "Disable" : "Enable"}">${u.active !== false ? "On" : "Off"}</button>
                                <button class="poll-delete-btn" data-delete-wu="${esc(u.id)}" title="Delete" style="background:none;border:none;cursor:pointer;color:var(--text2);font-size:16px;padding:2px 6px">&times;</button>
                            </td>
                        </tr>`;
                    }).join("")}
                </tbody>
            </table>
        `;
        container.querySelectorAll("[data-toggle-wu]").forEach(btn => {
            btn.addEventListener("click", async () => {
                await api(`/api/world-updates/${btn.dataset.toggleWu}/toggle`, { method: "POST" });
                loadWorldUpdates();
            });
        });
        container.querySelectorAll("[data-delete-wu]").forEach(btn => {
            btn.addEventListener("click", async () => {
                await api(`/api/world-updates/${btn.dataset.deleteWu}`, { method: "DELETE" });
                loadWorldUpdates();
            });
        });
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load: ${esc(e.message)}</p>`;
    }
}

async function loadEventList() {
    const container = document.getElementById("evt-list");
    if (!container) return;

    try {
        const events = await api("/api/events");
        if (!events || events.length === 0) {
            container.innerHTML = '<p style="color:var(--text2);font-size:13px">No events recorded.</p>';
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead><tr><th>Date</th><th>Description</th><th>Segments</th><th>Applied</th><th>Actions</th></tr></thead>
                <tbody>
                    ${events.map(e => `
                        <tr>
                            <td>${esc(e.date || "")}</td>
                            <td>${esc(truncate(e.description || "", 60))}</td>
                            <td style="font-size:11px">${esc(truncate(formatSegments(e.affected_segments), 40))}</td>
                            <td>${e.applied ? '<span class="badge badge-complete">Yes</span>' : '<span class="badge badge-pending">No</span>'}</td>
                            <td style="white-space:nowrap">
                                <button class="btn btn-sm" data-preview-evt="${esc(String(e.event_id))}">Preview</button>
                                ${!e.applied ? `<button class="btn btn-sm btn-primary" style="margin-left:4px" data-apply-evt="${esc(String(e.event_id))}">Apply</button>` : ""}
                            </td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
            <div id="evt-preview-result"></div>
        `;

        // Preview handlers
        container.querySelectorAll("button[data-preview-evt]").forEach(btn => {
            btn.addEventListener("click", async () => {
                const previewDiv = document.getElementById("evt-preview-result");
                if (!previewDiv) return;
                try {
                    const preview = await api(`/api/events/${btn.dataset.previewEvt}/preview`);
                    previewDiv.innerHTML = `
                        <div class="card" style="margin-top:12px">
                            <div class="section-title">Preview: Event ${esc(String(btn.dataset.previewEvt))}</div>
                            <p style="font-size:13px">Profiles affected: <strong>${preview.profiles_affected || 0}</strong></p>
                            ${preview.changes ? `<pre style="font-size:11px;color:var(--text2);overflow-x:auto;max-height:200px">${esc(JSON.stringify(preview.changes, null, 2))}</pre>` : ""}
                        </div>
                    `;
                } catch (e) {
                    previewDiv.innerHTML = `<p style="color:var(--text2);margin-top:8px">Preview failed: ${esc(e.message)}</p>`;
                }
            });
        });

        // Apply handlers
        container.querySelectorAll("button[data-apply-evt]").forEach(btn => {
            btn.addEventListener("click", async () => {
                if (!confirm("Apply this event? This will modify affected profiles.")) return;
                try {
                    await api(`/api/events/${btn.dataset.applyEvt}/apply`, { method: "POST" });
                    loadEventList();
                    loadStats();
                } catch (e) {
                    alert(`Error applying event: ${e.message}`);
                }
            });
        });
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load events: ${esc(e.message)}</p>`;
    }
}

function formatSegments(segments) {
    if (!segments) return "--";
    if (typeof segments === "string") return segments;
    if (Array.isArray(segments)) {
        return segments.map(s => `${s.variable || ""}=${s.value || ""}`).join(", ");
    }
    return JSON.stringify(segments);
}

// --- View 6: Data Sources ---

function renderSourcesView(el) {
    el.innerHTML = '<h2>Data Sources</h2><div id="sources-content"><p style="color:var(--text2)">Loading...</p></div>';
    loadSourcesData();
}

async function loadSourcesData() {
    const container = document.getElementById("sources-content");
    if (!container) return;

    try {
        const data = await api("/api/sources");
        const summary = data.summary;
        const sources = data.sources;

        const statusIcon = (s) => {
            if (s === "loaded") return '<span style="color:var(--green);font-weight:700">LOADED</span>';
            if (s === "partial") return '<span style="color:var(--orange);font-weight:700">PARTIAL</span>';
            return '<span style="color:var(--red);font-weight:700">MISSING</span>';
        };

        const accessIcon = (a) => {
            if (a === "public_api") return '<span class="badge badge-complete">Public API</span>';
            if (a === "public_download") return '<span class="badge badge-complete">Public Download</span>';
            if (a === "free_registration") return '<span class="badge badge-live">Free Registration</span>';
            return '<span class="badge badge-pending">Request Required</span>';
        };

        let html = `
            <div class="card">
                <div class="section-title">Coverage Summary</div>
                <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:16px">
                    <div style="text-align:center">
                        <div style="font-size:28px;font-weight:700;color:var(--green)">${summary.loaded}</div>
                        <div style="font-size:11px;color:var(--text2)">Loaded</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:28px;font-weight:700;color:var(--orange)">${summary.partial}</div>
                        <div style="font-size:11px;color:var(--text2)">Partial</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:28px;font-weight:700;color:var(--red)">${summary.missing}</div>
                        <div style="font-size:11px;color:var(--text2)">Missing</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:28px;font-weight:700;color:var(--text)">${summary.loaded_variables}/${summary.total_variables}</div>
                        <div style="font-size:11px;color:var(--text2)">Variables Loaded</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:28px;font-weight:700;color:var(--text)">${summary.profile_count}</div>
                        <div style="font-size:11px;color:var(--text2)">Profiles</div>
                    </div>
                </div>
                <div style="height:8px;background:var(--surface2);border-radius:4px;overflow:hidden">
                    <div style="height:100%;width:${Math.round(summary.loaded_variables / summary.total_variables * 100)}%;background:var(--accent);border-radius:4px"></div>
                </div>
                <div style="font-size:11px;color:var(--text2);margin-top:4px">${Math.round(summary.loaded_variables / summary.total_variables * 100)}% variable coverage</div>
            </div>
        `;

        // Source cards
        for (const src of sources) {
            const varBar = src.variables_total > 0
                ? `<div style="height:6px;background:var(--surface2);border-radius:3px;overflow:hidden;margin:8px 0">
                     <div style="height:100%;width:${Math.round(src.variables_loaded / src.variables_total * 100)}%;background:${src.status === 'loaded' ? 'var(--green)' : src.status === 'partial' ? 'var(--orange)' : 'var(--red)'};border-radius:3px"></div>
                   </div>`
                : "";

            html += `
                <div class="card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                        <div>
                            <h3 style="margin:0;font-size:15px">${esc(src.name)} <span style="font-weight:400;color:var(--text2);font-size:12px">— ${esc(src.full_name)}</span></h3>
                            <div style="font-size:12px;color:var(--text2);margin-top:2px">${esc(src.layer)}</div>
                        </div>
                        <div style="text-align:right">
                            ${statusIcon(src.status)}
                            <div style="font-size:11px;color:var(--text2);margin-top:2px">${src.variables_loaded}/${src.variables_total} vars</div>
                        </div>
                    </div>
                    ${varBar}
                    <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;margin-bottom:8px">
                        <div><span style="color:var(--text2)">Provider:</span> ${esc(src.provider)}</div>
                        <div><span style="color:var(--text2)">Format:</span> ${esc(src.format)}</div>
                        <div><span style="color:var(--text2)">Update:</span> ${esc(src.update_cycle)}</div>
                        <div><span style="color:var(--text2)">Records:</span> ${esc(src.records)}</div>
                    </div>
                    <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
                        ${accessIcon(src.access_level)}
                        <a href="${esc(src.url)}" target="_blank" style="font-size:12px;color:var(--accent);text-decoration:none">${esc(src.url)}</a>
                    </div>
                    <div style="font-size:11px;color:var(--text2);margin-bottom:4px">${esc(src.access)}</div>

                    <details style="margin-top:8px">
                        <summary style="cursor:pointer;font-size:12px;color:var(--text2)">Variables (${src.variables_total})</summary>
                        <div style="padding:8px 0;display:flex;flex-wrap:wrap;gap:4px">
                            ${src.variables_present.map(v => `<span class="badge badge-complete">${esc(v)}</span>`).join("")}
                            ${src.variables_missing.map(v => `<span class="badge badge-pending" style="text-decoration:line-through;opacity:0.6">${esc(v)}</span>`).join("")}
                        </div>
                    </details>
                </div>
            `;
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load sources: ${esc(e.message)}</p>`;
    }
}

// Load sidebar stats
async function loadStats() {
    try {
        stats = await api("/api/stats");
        document.getElementById("stat-profiles").textContent = stats.profile_count || 0;
        document.getElementById("stat-archetypes").textContent = stats.archetype_count || 0;
        document.getElementById("stat-polls").textContent = stats.polls_run || 0;
    } catch (e) {
        console.error("Failed to load stats:", e);
    }
}

// Utility: escape HTML
function esc(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
}

// Init
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".nav-link").forEach(el => {
        el.addEventListener("click", () => navigate(el.dataset.view));
    });
    loadStats();
    render();
});
