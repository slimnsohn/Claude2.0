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

// ---- Node test export (no-op inside Apps Script) ---------------------------

if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_
  };
}
