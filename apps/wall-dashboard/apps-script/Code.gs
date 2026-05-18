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

// ---- Amtrak schedule read --------------------------------------------------

/**
 * Read the AmtrakSchedule tab -> [{ trainNum, direction, glenviewTime, days }].
 * The tab is machine-written by refreshAmtrakSchedule. Skips blank rows.
 * Returns [] if the tab does not exist yet. Cached 1 hour.
 */
function getAmtrakSchedule_() {
  return cachedFetch_('amtrak', 3600, function () {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('AmtrakSchedule');
    if (!sheet) return [];
    var rows = sheet.getDataRange().getValues();
    var out = [];
    for (var i = 1; i < rows.length; i++) {
      var trainNum = String(rows[i][0]).trim();
      if (!trainNum) continue;
      out.push({
        trainNum: trainNum,
        direction: String(rows[i][1]).trim(),
        glenviewTime: String(rows[i][2]).trim(),
        days: String(rows[i][3]).trim()
      });
    }
    return out;
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
    trains: { available: false, list: [], message: 'Trains unavailable' },
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

  // Trains
  try {
    var combined = getCombinedTrains_(now, tz, config, {
      windowMin: parseInt(config.train_window_min, 10),
      maxCount: parseInt(config.max_trains, 10),
      respectHours: true
    });
    data.trains = {
      available: combined.list.length > 0,
      list: combined.list,
      message: combined.message
    };
  } catch (err) {
    data.trains = { available: false, list: [], message: 'Trains unavailable' };
  }

  return data;
}

/**
 * Build the trains-only payload for the phone widget and JSON route:
 * the next 3 trains regardless of hour or window.
 */
function buildTrainsData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  var data = {
    location: 'Northbrook',
    trains: { available: false, list: [], message: 'Trains unavailable' },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };
  try {
    var config = getConfig_();
    var combined = getCombinedTrains_(now, tz, config, {
      windowMin: 100000,     // effectively no window
      maxCount: 3,
      respectHours: false
    });
    data.trains = {
      available: combined.list.length > 0,
      list: combined.list,
      message: combined.message
    };
  } catch (err) {
    data.trains = { available: false, list: [], message: 'Trains unavailable' };
  }
  return data;
}

/** Public wrapper so the page can re-pull dashboard data via google.script.run. */
function dashboardData() {
  return buildDashboardData_();
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

/** Inject the trains payload into Trains.html and return HtmlOutput. */
function renderTrainsOnly_(data) {
  var t = HtmlService.createTemplateFromFile('Trains');
  t.dataJson = JSON.stringify(data).replace(/<\/script>/gi, '<\\/script>');
  return t.evaluate()
    .setTitle('Northbrook Trains')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Serve the trains payload as JSON (for a future phone app). */
function renderTrainsJson_(data) {
  var trains = data.trains.list.map(function (t) {
    return {
      type: t.type,
      time: t.time,
      countdown_min: t.countdownMin,
      countdown_str: t.countdown
    };
  });
  var payload = { location: data.location, trains: trains, updated_at: data.updatedAt };
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
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
  var m = String(str).trim().match(/^(\d{1,4}):(\d{2}):(\d{2})$/);
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

/** Pure: GTFS trip_headsign -> 'SB' toward Chicago, else 'NB'. */
function headsignDirection_(headsign) {
  return String(headsign).trim() === 'Chicago' ? 'SB' : 'NB';
}

/** Pure: a calendar.txt row -> 7-char Mon..Sun bitstring. */
function calendarBitstring_(row) {
  var days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
              'saturday', 'sunday'];
  return days.map(function (d) {
    return String(row[d]).trim() === '1' ? '1' : '0';
  }).join('');
}

/** Pure: bitwise-OR two 7-char weekday bitstrings. */
function unionBits_(a, b) {
  var out = '';
  for (var i = 0; i < 7; i++) {
    out += (a.charAt(i) === '1' || b.charAt(i) === '1') ? '1' : '0';
  }
  return out;
}

/** Pure: is YYYYMMDD `today` within [start, end] inclusive? */
function dateInWindow_(today, start, end) {
  return today >= start && today <= end;
}

/**
 * Pure: GTFS tables { routes, trips, stopTimes, calendar } + today's YYYYMMDD
 * -> [{ trainNum, direction, glenviewTime, days }], one per (train, direction),
 * sorted by Glenview time. Keeps only Hiawatha/Empire Builder trips that stop
 * at Glenview under a service active today; unions weekday bits per train.
 */
function extractAmtrakRows_(tables, todayYmd) {
  var WANTED = { 'Hiawatha Service': true, 'Empire Builder': true };
  var routeIds = {};
  tables.routes.forEach(function (r) {
    if (WANTED[String(r.route_long_name).trim()]) routeIds[r.route_id] = true;
  });

  var calById = {};
  tables.calendar.forEach(function (c) { calById[c.service_id] = c; });

  var glnDeparture = {};
  tables.stopTimes.forEach(function (st) {
    if (String(st.stop_id).trim() === 'GLN') {
      glnDeparture[st.trip_id] = st.departure_time;
    }
  });

  var byKey = {};
  tables.trips.forEach(function (t) {
    if (!routeIds[t.route_id]) return;
    var cal = calById[t.service_id];
    if (!cal) return;
    if (!dateInWindow_(todayYmd, cal.start_date, cal.end_date)) return;
    var departure = glnDeparture[t.trip_id];
    if (departure == null) return;

    var trainNum = String(t.trip_short_name).trim();
    var direction = headsignDirection_(t.trip_headsign);
    var bits = calendarBitstring_(cal);
    var key = trainNum + '|' + direction;
    // Same train+direction across multiple service IDs: union the weekday
    // bits. The Glenview time is identical across a train's services, so
    // the first-seen time is kept.
    if (byKey[key]) {
      byKey[key].days = unionBits_(byKey[key].days, bits);
    } else {
      byKey[key] = {
        trainNum: trainNum,
        direction: direction,
        glenviewMinutes: gtfsTimeToMinutes_(departure),
        days: bits
      };
    }
  });

  var rows = [];
  for (var k in byKey) {
    if (byKey.hasOwnProperty(k)) rows.push(byKey[k]);
  }
  rows.sort(function (a, b) { return a.glenviewMinutes - b.glenviewMinutes; });
  return rows.map(function (r) {
    return {
      trainNum: r.trainNum,
      direction: r.direction,
      glenviewTime: minutesToHHMM_(r.glenviewMinutes),
      days: r.days
    };
  });
}

// ---- Amtrak GTFS refresh (I/O) ---------------------------------------------

/**
 * Download Amtrak's GTFS feed, extract the Glenview Hiawatha + Empire Builder
 * trains, and rewrite the AmtrakSchedule tab. Public (no trailing underscore)
 * so it can be run from the editor and used as a weekly trigger handler.
 */
function refreshAmtrakSchedule() {
  var resp = UrlFetchApp.fetch('https://content.amtrak.com/content/gtfs/GTFS.zip', {
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('GTFS download returned ' + resp.getResponseCode());
  }
  var need = { 'routes.txt': true, 'trips.txt': true, 'stop_times.txt': true, 'calendar.txt': true };
  var raw = {};
  Utilities.unzip(resp.getBlob()).forEach(function (f) {
    var base = f.getName().split('/').pop();
    if (need[base]) raw[base] = f.getDataAsString();
  });
  ['routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt'].forEach(function (n) {
    if (raw[n] == null) throw new Error('GTFS feed missing ' + n);
  });

  var tables = {
    routes: parseCsv_(raw['routes.txt']),
    trips: parseCsv_(raw['trips.txt']),
    stopTimes: parseCsv_(raw['stop_times.txt']),
    calendar: parseCsv_(raw['calendar.txt'])
  };
  var today = Utilities.formatDate(new Date(), 'America/Chicago', 'yyyyMMdd');
  var extracted = extractAmtrakRows_(tables, today);

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('AmtrakSchedule');
  if (!sheet) sheet = ss.insertSheet('AmtrakSchedule');
  sheet.clearContents();

  var values = [['train_num', 'direction', 'glenview_time', 'days']];
  extracted.forEach(function (r) {
    values.push([r.trainNum, r.direction, r.glenviewTime, r.days]);
  });
  // Plain-text format first, so "06:43" and bitstrings like "0000011" are not
  // coerced to a time or a number.
  var range = sheet.getRange(1, 1, values.length, 4);
  range.setNumberFormat('@');
  range.setValues(values);

  Logger.log('AmtrakSchedule refreshed: ' + extracted.length + ' trains for ' + today);
}

/**
 * Install (or re-install) the weekly trigger that runs refreshAmtrakSchedule.
 * Public so it can be run once from the editor. Idempotent — clears any
 * existing refreshAmtrakSchedule trigger first.
 */
function installAmtrakTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'refreshAmtrakSchedule') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('refreshAmtrakSchedule')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(3)
    .create();
  Logger.log('Weekly refreshAmtrakSchedule trigger installed (Mondays ~3 AM).');
}

// ---- Trains: orchestration -------------------------------------------------

/**
 * All Amtrak trains relevant to `now`: today's, plus tomorrow's with
 * passMinutes shifted +1440 so overnight lookups work. tz is the script
 * timezone string.
 */
function getAmtrakTrains_(now, tz) {
  var schedule = getAmtrakSchedule_();
  // Apps Script 'u' = 1(Mon)..7(Sun); % 7 maps to 0(Sun)..6(Sat).
  var dow = parseInt(Utilities.formatDate(now, tz, 'u'), 10) % 7;
  var today = computeAmtrakTrains_(schedule, dow);
  var tomorrow = computeAmtrakTrains_(schedule, (dow + 1) % 7).map(function (t) {
    return { type: t.type, passMinutes: t.passMinutes + 1440 };
  });
  return today.concat(tomorrow);
}

/**
 * Gather every train source (Amtrak + Metra), merge, and run selectTrains_.
 * `opts` = { windowMin, maxCount, respectHours }; display-hour bounds come
 * from config. A Metra feed failure must never drop the Amtrak trains.
 */
function getCombinedTrains_(now, tz, config, opts) {
  var all = getAmtrakTrains_(now, tz);
  try {
    all = all.concat(getMetraTrains_(now, tz, config));
  } catch (err) {
    // Metra unavailable — fall through with Amtrak only.
  }
  var nowMinutes = parseInt(Utilities.formatDate(now, tz, 'H'), 10) * 60
                 + parseInt(Utilities.formatDate(now, tz, 'm'), 10);
  var nowHour = Math.floor(nowMinutes / 60);
  return selectTrains_(all, nowMinutes, nowHour, {
    windowMin: opts.windowMin,
    maxCount: opts.maxCount,
    respectHours: opts.respectHours,
    startHour: parseInt(config.display_start_hour, 10),
    endHour: parseInt(config.display_end_hour, 10)
  });
}

// ---- Trains: time + day parsing (pure) -------------------------------------

/** Pure: "HH:MM" or "H:MM" -> minutes since midnight. Throws on bad input. */
function parseHHMM_(str) {
  var m = String(str).trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!m) throw new Error('Bad time: ' + str);
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

/**
 * Pure: a 7-char Mon..Sun weekday bitstring -> sorted day indices
 * (0=Sun..6=Sat). Position i (0=Mon) maps to index (i + 1) % 7.
 */
function parseDays_(bitstring) {
  var s = String(bitstring);
  var out = [];
  for (var i = 0; i < 7 && i < s.length; i++) {
    if (s.charAt(i) === '1') out.push((i + 1) % 7);
  }
  return out.sort(function (a, b) { return a - b; });
}

/**
 * Pure: Glenview "HH:MM" + direction -> Northbrook pass, minutes since
 * midnight. NB reaches Northbrook +3 min, SB -3 min. Wraps within 0..1439.
 */
function northbrookMinutes_(glenviewHHMM, direction) {
  var base = parseHHMM_(glenviewHHMM);
  var offset = (String(direction).trim().toUpperCase() === 'NB') ? 3 : -3;
  return ((base + offset) % 1440 + 1440) % 1440;
}

/** Pure: minutes -> "9 min" under an hour, "1h 9m" at/over an hour. */
function formatCountdown_(minutes) {
  if (minutes < 60) return minutes + ' min';
  return Math.floor(minutes / 60) + 'h ' + (minutes % 60) + 'm';
}

/** Pure: minutes since midnight (any value) -> "6:43 AM". Wraps mod 1440. */
function formatClockTime_(minutes) {
  var t = ((minutes % 1440) + 1440) % 1440;
  var h = Math.floor(t / 60), m = t % 60;
  var period = h < 12 ? 'AM' : 'PM';
  var h12 = h % 12;
  if (h12 === 0) h12 = 12;
  return h12 + ':' + (m < 10 ? '0' + m : '' + m) + ' ' + period;
}

/**
 * Pure: schedule rows + a day index (0=Sun..6=Sat) -> trains running that
 * day, each { type:'Amtrak', passMinutes }. Order follows the input rows.
 */
function computeAmtrakTrains_(rows, dayIndex) {
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    if (parseDays_(r.days).indexOf(dayIndex) < 0) continue;
    out.push({
      type: 'Amtrak',
      passMinutes: northbrookMinutes_(r.glenviewTime, r.direction)
    });
  }
  return out;
}

// ---- Trains: selection (pure) ----------------------------------------------

/**
 * Pure: pick the trains to show.
 * trains: [{ type, passMinutes }] (tomorrow's carry passMinutes + 1440).
 * nowMinutes / nowHour: current time. opts: { windowMin, maxCount,
 * respectHours, startHour, endHour }.
 * Returns { list:[{type,time,countdown}], message }. message is null when
 * list is non-empty.
 */
function selectTrains_(trains, nowMinutes, nowHour, opts) {
  var candidates = trains
    .filter(function (t) { return t.passMinutes >= nowMinutes; })
    .sort(function (a, b) { return a.passMinutes - b.passMinutes; });
  var next = candidates.length ? candidates[0] : null;

  function display(t) {
    var delta = t.passMinutes - nowMinutes;
    return {
      type: t.type,
      time: formatClockTime_(t.passMinutes),
      countdown: formatCountdown_(delta),
      countdownMin: delta
    };
  }

  var outsideHours = nowHour < opts.startHour || nowHour >= opts.endHour;
  if (opts.respectHours && outsideHours) {
    // Prefer the soonest upcoming train; fall back to the earliest of all
    // (a passed train represents tomorrow's run, same clock time mod 24h).
    var allSorted = trains.slice().sort(function (a, b) { return a.passMinutes - b.passMinutes; });
    var anyNext = candidates.length ? candidates[0]
                : (allSorted.length ? allSorted[0] : null);
    return anyNext
      ? { list: [], message: 'No train until ' + formatClockTime_(anyNext.passMinutes) }
      : { list: [], message: 'No more trains' };
  }

  var windowed = candidates
    .filter(function (t) { return t.passMinutes - nowMinutes <= opts.windowMin; })
    .slice(0, opts.maxCount);
  if (windowed.length) {
    return { list: windowed.map(display), message: null };
  }
  return next
    ? { list: [], message: 'No train in next ' + opts.windowMin
        + ' min — next: ' + formatClockTime_(next.passMinutes) }
    : { list: [], message: 'No more trains' };
}

// ---- Metra GTFS-Realtime (pure protobuf decoding) --------------------------

/**
 * Pure: generic protobuf wire-format decoder.
 * Returns { fieldNumber: [values] }. A varint value is a Number; a
 * length-delimited value is a { start, end } range into the same `bytes`
 * (sub-messages decode in place, no copying). 64-bit / 32-bit fields skipped.
 * `bytes` may be a Node Buffer, a Uint8Array, or a (possibly signed) byte
 * array — `& 0xff` normalizes each byte.
 */
function decodeProtobuf_(bytes, start, end) {
  var pos = start;
  var fields = {};
  function readVarint() {
    var result = 0, shift = 0, b;
    do {
      if (pos >= end) throw new Error('Truncated protobuf');
      b = bytes[pos++] & 0xff;
      result += (b & 0x7f) * Math.pow(2, shift);
      shift += 7;
    } while (b & 0x80);
    return result;
  }
  while (pos < end) {
    var tag = readVarint();
    var field = Math.floor(tag / 8), wire = tag & 7;
    if (wire === 0) {
      (fields[field] || (fields[field] = [])).push(readVarint());
    } else if (wire === 2) {
      var len = readVarint();
      (fields[field] || (fields[field] = [])).push({ start: pos, end: pos + len });
      pos += len;
    } else if (wire === 1) {
      pos += 8;
    } else if (wire === 5) {
      pos += 4;
    } else {
      throw new Error('Bad protobuf wire type: ' + wire);
    }
  }
  return fields;
}

/**
 * Pure: a train's arrival epoch (seconds) -> passMinutes, in the same
 * minutes-since-midnight space the Amtrak trains use.
 */
function metraPassMinutes_(arrivalEpoch, nowEpochSec, nowMinutes) {
  return nowMinutes + Math.round((arrivalEpoch - nowEpochSec) / 60);
}

/**
 * Fetch the Metra realtime feed and return [{ type:'Metra', passMinutes }]
 * for trains approaching the configured stop. Cached 45 s. Returns [] when
 * Metra is not configured (no token / stop id in the Config tab).
 */
function getMetraTrains_(now, tz, config) {
  if (!config.metra_api_token || !config.metra_stop_id) return [];
  // Cached value is the parsed result for config.metra_stop_id; a stop-id
  // change would be masked for up to 45 s (fine — stop ids are static).
  var parsed = cachedFetch_('metra', 45, function () {
    var url = 'https://gtfspublic.metrarr.com/gtfs/public/tripupdates?api_token='
      + encodeURIComponent(config.metra_api_token);
    var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) {
      throw new Error('Metra feed returned ' + resp.getResponseCode());
    }
    return parseTripUpdates_(resp.getBlob().getBytes(), config.metra_stop_id);
  });
  var nowEpochSec = Math.floor(now.getTime() / 1000);
  var nowMinutes = parseInt(Utilities.formatDate(now, tz, 'H'), 10) * 60
                 + parseInt(Utilities.formatDate(now, tz, 'm'), 10);
  return parsed.map(function (t) {
    return {
      type: 'Metra',
      passMinutes: metraPassMinutes_(t.arrivalEpoch, nowEpochSec, nowMinutes)
    };
  });
}

/** Internal: StopTimeEvent.time (field 2) from an arrival/departure field. */
function stopTimeEventTime_(bytes, eventField) {
  if (!eventField) return null;
  var ev = decodeProtobuf_(bytes, eventField[0].start, eventField[0].end);
  return ev[2] ? ev[2][0] : null;
}

/**
 * Pure: decode a GTFS-Realtime tripUpdates feed (raw bytes) -> a list of
 * { routeId, tripId, arrivalEpoch } for every stop_time_update whose stop_id
 * equals `stopId`. Uses the arrival time, falling back to departure.
 */
function parseTripUpdates_(bytes, stopId) {
  var root = decodeProtobuf_(bytes, 0, bytes.length);
  var entities = root[2] || [];                       // FeedMessage.entity
  var out = [];
  for (var i = 0; i < entities.length; i++) {
    var e = decodeProtobuf_(bytes, entities[i].start, entities[i].end);
    if (!e[3]) continue;                              // FeedEntity.trip_update
    var tu = decodeProtobuf_(bytes, e[3][0].start, e[3][0].end);
    var routeId = '', tripId = '';
    if (tu[1]) {                                      // TripUpdate.trip
      var trip = decodeProtobuf_(bytes, tu[1][0].start, tu[1][0].end);
      if (trip[1]) tripId = pbString_(bytes, trip[1][0]);   // trip_id
      if (trip[5]) routeId = pbString_(bytes, trip[5][0]);  // route_id
    }
    var stus = tu[2] || [];                           // TripUpdate.stop_time_update
    for (var j = 0; j < stus.length; j++) {
      var stu = decodeProtobuf_(bytes, stus[j].start, stus[j].end);
      if (!stu[4] || pbString_(bytes, stu[4][0]) !== stopId) continue; // stop_id
      var epoch = stopTimeEventTime_(bytes, stu[2]);  // arrival
      if (epoch == null) epoch = stopTimeEventTime_(bytes, stu[3]); // departure
      if (epoch == null) continue;
      out.push({ routeId: routeId, tripId: tripId, arrivalEpoch: epoch });
    }
  }
  return out;
}

/**
 * Pure: a { start, end } byte range -> string. GTFS-RT ids (route_id,
 * trip_id, stop_id) are ASCII, so a per-byte char code is sufficient.
 */
function pbString_(bytes, range) {
  var s = '';
  for (var i = range.start; i < range.end; i++) {
    s += String.fromCharCode(bytes[i] & 0xff);
  }
  return s;
}

// ---- Entry point -----------------------------------------------------------

function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    var route = routeView_(p.view, p.format);
    if (route === 'trainsJson') return renderTrainsJson_(buildTrainsData_());
    if (route === 'trains') return renderTrainsOnly_(buildTrainsData_());
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
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_,
    formatCountdown_: formatCountdown_,
    formatClockTime_: formatClockTime_,
    computeAmtrakTrains_: computeAmtrakTrains_,
    selectTrains_: selectTrains_,
    decodeProtobuf_: decodeProtobuf_,
    pbString_: pbString_,
    parseTripUpdates_: parseTripUpdates_,
    metraPassMinutes_: metraPassMinutes_
  };
}
