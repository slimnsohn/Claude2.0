/**
 * Wall Dashboard — Apps Script web app.
 * Pure helpers are exported at the bottom for Node unit tests.
 */

// ---- Routing ---------------------------------------------------------------

/** Pure: map URL params to a route name. */
function routeView_(view, format) {
  if (view === 'trains' && format === 'json') return 'trainsJson';
  if (view === 'trains') return 'trains';
  return 'dashboard';
}

// ---- Data assembly ---------------------------------------------------------

/**
 * Build the data object the dashboard renders.
 * Step 1: placeholder weather + trains. Step 2 replaces the weather block.
 */
function buildDashboardData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  return {
    location: 'Glenview',
    dateStr: Utilities.formatDate(now, tz, 'EEE MMM d'),
    timeStr: Utilities.formatDate(now, tz, 'h:mm a'),
    weather: {
      available: true,
      temp: 72,
      feelsLike: 70,
      condition: 'Partly cloudy (placeholder)',
      hourly: [
        { label: '1p', temp: 74, precip: 10 },
        { label: '2p', temp: 76, precip: 15 },
        { label: '3p', temp: 78, precip: 20 },
        { label: '4p', temp: 77, precip: 35 },
        { label: '5p', temp: 74, precip: 40 },
        { label: '6p', temp: 70, precip: 20 },
        { label: '7p', temp: 67, precip: 5 }
      ]
    },
    trains: {
      available: false,
      list: [],
      message: 'Trains — coming in a later step'
    },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };
}

// ---- Rendering -------------------------------------------------------------

/** Inject the data object as JSON into Dashboard.html and return HtmlOutput. */
function renderDashboard_(data) {
  var t = HtmlService.createTemplateFromFile('Dashboard');
  t.dataJson = JSON.stringify(data);
  return t.evaluate()
    .setTitle('Wall Dashboard')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Minimal error page that still auto-refreshes. */
function errorPage_(message) {
  return HtmlService.createHtmlOutput(
    '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;' +
    'font-family:sans-serif;font-size:32px;padding:48px">' +
    'Dashboard error — retrying<br><small style="font-size:18px;color:#888">' +
    message + '</small>' +
    '<meta http-equiv="refresh" content="60"></body>');
}

// ---- Entry point -----------------------------------------------------------

function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    var route = routeView_(p.view, p.format);
    if (route !== 'dashboard') {
      return HtmlService.createHtmlOutput(
        '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;' +
        'font-family:sans-serif;font-size:32px;padding:48px">' +
        'Trains view — coming in a later step</body>');
    }
    return renderDashboard_(buildDashboardData_());
  } catch (err) {
    return errorPage_(String(err));
  }
}

// ---- Node test export (no-op inside Apps Script) ---------------------------

if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_
  };
}
