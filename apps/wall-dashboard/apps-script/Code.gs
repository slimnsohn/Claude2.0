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

// ---- Weather window (pure) -------------------------------------------------

/**
 * Pure: which hours of weather to display.
 * Before flipHour -> rest of today (next full hour..endHour).
 * At/after flipHour -> tomorrow 7..endHour.
 */
function getWeatherWindow_(nowHour, flipHour, endHour) {
  var hours = [];
  if (nowHour < flipHour) {
    for (var h = nowHour + 1; h <= endHour; h++) hours.push(h);
    return { dayOffset: 0, hours: hours };
  }
  for (var t = 7; t <= endHour; t++) hours.push(t);
  return { dayOffset: 1, hours: hours };
}

/**
 * Pure: apparent temperature in F.
 * Heat index when hot+humid, wind chill when cold+windy, else the temp itself.
 * Uses the NWS Rothfusz heat-index and the standard wind-chill regressions.
 */
function feelsLike_(tempF, humidityPct, windMph) {
  if (tempF == null) return null;
  if (tempF >= 80 && humidityPct != null) {
    var T = tempF, R = humidityPct;
    var hi = -42.379 + 2.04901523 * T + 10.14333127 * R
      - 0.22475541 * T * R - 0.00683783 * T * T - 0.05481717 * R * R
      + 0.00122874 * T * T * R + 0.00085282 * T * R * R
      - 0.00000199 * T * T * R * R;
    return Math.round(hi);
  }
  if (tempF <= 50 && windMph >= 3) {
    var v = Math.pow(windMph, 0.16);
    return Math.round(35.74 + 0.6215 * tempF - 35.75 * v + 0.4275 * tempF * v);
  }
  return Math.round(tempF);
}

/** Pure: find the hourly entry whose hourKey equals key, or null. */
function matchHour_(hourly, key) {
  for (var i = 0; i < hourly.length; i++) {
    if (hourly[i].hourKey === key) return hourly[i];
  }
  return null;
}

/**
 * Pure: US AQI value -> { category, level, alert }.
 * level is good|moderate|unhealthy for styling; alert is true for 51+.
 */
function aqiInfo_(value) {
  if (value <= 50)  return { category: 'Good', level: 'good', alert: false };
  if (value <= 100) return { category: 'Moderate', level: 'moderate', alert: true };
  if (value <= 150) return { category: 'Unhealthy for Sensitive', level: 'unhealthy', alert: true };
  if (value <= 200) return { category: 'Unhealthy', level: 'unhealthy', alert: true };
  if (value <= 300) return { category: 'Very Unhealthy', level: 'unhealthy', alert: true };
  return { category: 'Hazardous', level: 'unhealthy', alert: true };
}

/** Pure: hour 0-23 -> compact label like "9a" / "1p" / "12p". */
function formatHourLabel_(hour) {
  var period = hour < 12 ? 'a' : 'p';
  var hr = hour % 12;
  if (hr === 0) hr = 12;
  return hr + period;
}

// ---- Caching ---------------------------------------------------------------

/**
 * Run fn() at most once per ttlSec, caching the JSON-serializable result.
 * On a fetch failure, serve the last good value (kept for 6 h) if one exists.
 */
function cachedFetch_(key, ttlSec, fn) {
  var cache = CacheService.getScriptCache();
  var hit = cache.get(key);
  if (hit) return JSON.parse(hit);
  try {
    var fresh = fn();
    var serialized = JSON.stringify(fresh);
    cache.put(key, serialized, ttlSec);
    cache.put(key + '__last_good', serialized, 21600);
    return fresh;
  } catch (err) {
    var lastGood = cache.get(key + '__last_good');
    if (lastGood) return JSON.parse(lastGood);
    throw err;
  }
}

// ---- Config ----------------------------------------------------------------

/** Read the Config tab into a {key: value} object. Cached 5 min. */
function getConfig_() {
  return cachedFetch_('config', 300, function () {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Config');
    if (!sheet) throw new Error('Config sheet tab not found');
    var rows = sheet.getDataRange().getValues();
    var cfg = {};
    for (var i = 1; i < rows.length; i++) {
      var key = String(rows[i][0]).trim();
      if (key) cfg[key] = rows[i][1];
    }
    return cfg;
  });
}

// ---- Weather fetch ---------------------------------------------------------

/**
 * One-time helper: resolve the NWS hourly-forecast URL and write it into the
 * Config tab. Run manually from the editor (Run -> bootstrapNwsUrl).
 */
function bootstrapNwsUrl() {
  var config = getConfig_();
  var pointsUrl = 'https://api.weather.gov/points/' + config.nws_lat + ',' + config.nws_lon;
  var resp = UrlFetchApp.fetch(pointsUrl, {
    headers: { 'User-Agent': config.nws_user_agent },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('NWS /points returned ' + resp.getResponseCode());
  }
  var forecastHourly = JSON.parse(resp.getContentText()).properties.forecastHourly;
  Logger.log('forecastHourly URL: ' + forecastHourly);
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Config');
  var rows = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]).trim() === 'nws_forecast_hourly_url') {
      sheet.getRange(i + 1, 2).setValue(forecastHourly);
      Logger.log('Wrote URL to Config row ' + (i + 1));
      return;
    }
  }
  throw new Error('Config row nws_forecast_hourly_url not found');
}

/**
 * Fetch the NWS hourly forecast, reduced to the fields the dashboard needs.
 * Returns { hourly: [{hourKey, temp, precip, humidity, windMph, condition}] }.
 * Cached 15 min.
 */
function getWeather_(config) {
  return cachedFetch_('weather', 900, function () {
    var url = config.nws_forecast_hourly_url;
    if (!url) throw new Error('nws_forecast_hourly_url not set — run bootstrapNwsUrl first');
    var resp = UrlFetchApp.fetch(url, {
      headers: { 'User-Agent': config.nws_user_agent },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error('NWS hourly returned ' + resp.getResponseCode());
    }
    var periods = JSON.parse(resp.getContentText()).properties.periods;
    var hourly = periods.slice(0, 48).map(function (p) {
      return {
        hourKey: Utilities.formatDate(new Date(p.startTime), 'America/Chicago', 'yyyy-MM-dd-HH'),
        temp: p.temperature,
        precip: (p.probabilityOfPrecipitation && p.probabilityOfPrecipitation.value) || 0,
        humidity: (p.relativeHumidity && p.relativeHumidity.value != null)
          ? p.relativeHumidity.value : null,
        windMph: parseInt(p.windSpeed, 10) || 0,
        condition: p.shortForecast
      };
    });
    return { hourly: hourly };
  });
}

/**
 * Fetch the current US AQI from Open-Meteo (no auth). Reuses the Config
 * lat/lon. Returns { value: <int> }. Cached 30 min.
 */
function getAqi_(config) {
  return cachedFetch_('aqi', 1800, function () {
    var url = 'https://air-quality-api.open-meteo.com/v1/air-quality'
      + '?latitude=' + config.nws_lat
      + '&longitude=' + config.nws_lon
      + '&current=us_aqi&timezone=America/Chicago';
    var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) {
      throw new Error('Open-Meteo AQI returned ' + resp.getResponseCode());
    }
    var current = JSON.parse(resp.getContentText()).current;
    if (!current || current.us_aqi == null) {
      throw new Error('AQI response missing us_aqi');
    }
    return { value: Math.round(current.us_aqi) };
  });
}

// ---- Data assembly ---------------------------------------------------------

/** Build the data object the dashboard renders, with live weather + AQI. */
function buildDashboardData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  var data = {
    location: 'Glenview',
    dateStr: Utilities.formatDate(now, tz, 'EEE MMM d'),
    timeStr: Utilities.formatDate(now, tz, 'h:mm a'),
    aqi: { available: false },
    weather: { available: false },
    trains: { available: false, list: [], message: 'Trains — coming in a later step' },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };

  var config;
  try {
    config = getConfig_();
  } catch (err) {
    return data; // no config -> everything stays unavailable
  }

  // Weather
  try {
    var weather = getWeather_(config);
    var nowHour = parseInt(Utilities.formatDate(now, tz, 'H'), 10);
    var flipHour = parseInt(config.weather_flip_hour, 10);
    var endHour = parseInt(config.weather_end_hour, 10);
    if (isNaN(flipHour) || isNaN(endHour)) {
      throw new Error('weather_flip_hour / weather_end_hour missing or invalid in Config');
    }
    var win = getWeatherWindow_(nowHour, flipHour, endHour);
    var hourly = win.hours.map(function (h) {
      var match = matchHour_(weather.hourly, hourKeyFor_(now, win.dayOffset, h, tz));
      return {
        label: formatHourLabel_(h),
        temp: match ? match.temp : null,
        precip: match ? match.precip : null
      };
    });
    var current = matchHour_(weather.hourly, hourKeyFor_(now, 0, nowHour, tz));
    data.weather = {
      available: true,
      temp: current ? current.temp : null,
      feelsLike: current ? feelsLike_(current.temp, current.humidity, current.windMph) : null,
      condition: current ? current.condition : '',
      hourly: hourly
    };
  } catch (err) {
    data.weather = { available: false, error: String(err) };
  }

  // Air quality
  try {
    var aqiVal = getAqi_(config).value;
    var info = aqiInfo_(aqiVal);
    data.aqi = {
      available: true,
      value: aqiVal,
      category: info.category,
      level: info.level,
      alert: info.alert
    };
  } catch (err) {
    data.aqi = { available: false, error: String(err) };
  }

  return data;
}

/** Build the 'yyyy-MM-dd-HH' key for now + dayOffset days at the given hour. */
function hourKeyFor_(now, dayOffset, hour, tz) {
  var d = new Date(now.getTime() + dayOffset * 86400000);
  var hh = hour < 10 ? '0' + hour : '' + hour;
  return Utilities.formatDate(d, tz, 'yyyy-MM-dd') + '-' + hh;
}

// ---- Rendering -------------------------------------------------------------

/** Inject the data object as JSON into Dashboard.html and return HtmlOutput. */
function renderDashboard_(data) {
  var t = HtmlService.createTemplateFromFile('Dashboard');
  t.dataJson = JSON.stringify(data).replace(/<\/script>/gi, '<\\/script>');
  return t.evaluate()
    .setTitle('Wall Dashboard')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Minimal error page that still auto-refreshes. */
function errorPage_(message) {
  var safeMessage = message.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  return HtmlService.createHtmlOutput(
    '<head><meta http-equiv="refresh" content="60"></head>' +
    '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;' +
    'font-family:sans-serif;font-size:32px;padding:48px">' +
    'Dashboard error — retrying<br><small style="font-size:18px;color:#888">' +
    safeMessage + '</small>' +
    '</body>');
}

// ---- Amtrak GTFS extraction (pure) -----------------------------------------

/** Pure: split one CSV line into fields, honoring "quoted" fields. */
function splitCsvLine_(line) {
  var out = [], cur = '', inQ = false;
  for (var i = 0; i < line.length; i++) {
    var c = line.charAt(i);
    if (inQ) {
      if (c === '"') {
        if (line.charAt(i + 1) === '"') { cur += '"'; i++; }
        else inQ = false;
      } else { cur += c; }
    } else if (c === '"') {
      inQ = true;
    } else if (c === ',') {
      out.push(cur); cur = '';
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out;
}

/** Pure: CSV text -> array of objects keyed by the header row. */
function parseCsv_(text) {
  var lines = String(text).split(/\r?\n/);
  if (lines.length < 2) return [];
  var headers = splitCsvLine_(lines[0]);
  var rows = [];
  for (var i = 1; i < lines.length; i++) {
    if (lines[i] === '') continue;
    var fields = splitCsvLine_(lines[i]);
    var obj = {};
    for (var j = 0; j < headers.length; j++) {
      obj[headers[j]] = j < fields.length ? fields[j] : '';
    }
    rows.push(obj);
  }
  return rows;
}

/** Pure: GTFS "H:MM:SS" (hours may exceed 24) -> minutes since midnight 0..1439. */
function gtfsTimeToMinutes_(str) {
  var m = String(str).trim().match(/^(\d{1,3}):(\d{2}):(\d{2})$/);
  if (!m) throw new Error('Bad GTFS time: ' + str);
  var total = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
  return ((total % 1440) + 1440) % 1440;
}

/** Pure: minutes since midnight -> "HH:MM" 24-hour, zero-padded. */
function minutesToHHMM_(minutes) {
  var t = ((minutes % 1440) + 1440) % 1440;
  var h = Math.floor(t / 60), m = t % 60;
  return (h < 10 ? '0' + h : '' + h) + ':' + (m < 10 ? '0' + m : '' + m);
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
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_
  };
}
