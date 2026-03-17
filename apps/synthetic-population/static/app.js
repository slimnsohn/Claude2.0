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
        case "events": renderEventsView(app); break;
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

        btn.disabled = true;
        progress.style.display = "block";
        progress.textContent = "Creating poll...";

        try {
            const body = { question };
            if (snapshotId) body.snapshot_id = snapshotId;
            const result = await api("/api/polls", { method: "POST", body });
            const pollId = result.poll_id;
            progress.textContent = "Poll created. Awaiting responses...";

            // Poll for completion
            const timer = setInterval(async () => {
                try {
                    const poll = await api(`/api/polls/${pollId}`);
                    if (poll.status === "complete") {
                        clearInterval(timer);
                        navigate("results", { pollId });
                    } else {
                        progress.textContent = `Status: ${poll.status || "processing"}...`;
                    }
                } catch (e) {
                    clearInterval(timer);
                    progress.textContent = `Error checking status: ${e.message}`;
                    btn.disabled = false;
                }
            }, 3000);
            pollTimers[pollId] = timer;
        } catch (e) {
            progress.textContent = `Error: ${e.message}`;
            btn.disabled = false;
        }
    });
}

async function loadRecentPolls() {
    const container = document.getElementById("poll-recent");
    if (!container) return;
    try {
        const polls = await api("/api/polls");
        const recent = (polls || []).slice(0, 10);
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
                        <th>Snapshot</th>
                        <th>Result</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${recent.map(p => `
                        <tr data-poll-id="${esc(String(p.poll_id))}" style="cursor:pointer">
                            <td>${esc(truncate(p.question, 60))}</td>
                            <td>${esc(p.date || "")}</td>
                            <td>${snapshotBadge(p.snapshot_id)}</td>
                            <td>${esc(p.headline_result || "--")}</td>
                            <td>${statusBadge(p.status)}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `;
        container.querySelectorAll("tr[data-poll-id]").forEach(row => {
            row.addEventListener("click", () => {
                navigate("results", { pollId: row.dataset.pollId });
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
        const dist = poll.distribution || {};
        const yesVal = dist.yes || 0;
        const noVal = dist.no || 0;
        const unsureVal = dist.unsure || 0;
        const ci = poll.ci || {};
        const breakdowns = poll.breakdowns || {};
        const confidence = poll.mean_confidence;

        let html = `
            <div class="card">
                <h3 style="margin:0 0 8px">${esc(poll.question || "")}</h3>
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
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load results: ${esc(e.message)}</p>`;
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
            <select id="pop-education" class="select"><option value="">All Education</option><option value="high_school">High School</option><option value="some_college">Some College</option><option value="bachelors">Bachelors</option><option value="graduate">Graduate</option></select>
            <select id="pop-party" class="select"><option value="">All Party</option><option value="democrat">Democrat</option><option value="republican">Republican</option><option value="independent">Independent</option></select>
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
            populationFilters = { search: "", sex: "", race: "", education: "", party_id: "", state: "" };
            switch (qf) {
                case "democrats": populationFilters.party_id = "democrat"; break;
                case "republicans": populationFilters.party_id = "republican"; break;
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

    const params = new URLSearchParams();
    if (populationFilters.search) params.set("search", populationFilters.search);
    if (populationFilters.sex) params.set("sex", populationFilters.sex);
    if (populationFilters.race) params.set("race", populationFilters.race);
    if (populationFilters.education) params.set("education", populationFilters.education);
    if (populationFilters.party_id) params.set("party_id", populationFilters.party_id);
    if (populationFilters.state) params.set("state", populationFilters.state);

    try {
        const profiles = await api(`/api/profiles?${params.toString()}`);
        populationData = profiles || [];
        renderPopulationTable();
    } catch (e) {
        container.innerHTML = `<p style="color:var(--text2)">Failed to load profiles: ${esc(e.message)}</p>`;
    }
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

    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    ${cols.map(c => `<th data-sort="${c.key}">${c.label}${arrow(c.key)}</th>`).join("")}
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

        html += `<div class="section-title">Demographics</div><div class="card">`;
        const demoFields = ["profile_id", "age", "sex", "race", "education", "state", "party_id", "archetype_id", "income_bracket", "urban_rural", "religion", "age_bracket"];
        for (const key of demoFields) {
            if (p[key] != null) {
                html += `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid var(--border)">
                    <span style="color:var(--text2)">${esc(key)}</span>
                    <span style="color:var(--text);font-weight:500">${esc(String(p[key]))}</span>
                </div>`;
            }
        }
        html += `</div>`;

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

// --- View 5: Events ---

function renderEventsView(el) {
    el.innerHTML = `
        <h2>Events</h2>
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

    loadEventList();
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
