// State
let currentView = "poll";
let selectedPollId = null;
let stats = {};

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

// Placeholder views (implemented in subsequent tasks)
function renderPollView(el) {
    el.innerHTML = `
        <h2>Poll</h2>
        <div class="card">
            <div class="section-title">Ask a Question</div>
            <textarea class="textarea" placeholder="Ask your population anything..."></textarea>
            <div style="margin-top:12px">
                <button class="btn btn-primary">Run Poll</button>
            </div>
        </div>
        <p style="color:var(--text2);font-size:13px">Full implementation coming in next task...</p>
    `;
}
function renderResultsView(el) { el.innerHTML = '<h2>Results</h2><p style="color:var(--text2)">Select a poll to view results.</p>'; }
function renderPopulationView(el) { el.innerHTML = '<h2>Population</h2><p style="color:var(--text2)">Loading...</p>'; }
function renderBacktestView(el) { el.innerHTML = '<h2>Backtest</h2><p style="color:var(--text2)">Loading...</p>'; }
function renderEventsView(el) { el.innerHTML = '<h2>Events</h2><p style="color:var(--text2)">Loading...</p>'; }

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
    const div = document.createElement("div");
    div.textContent = str;
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
