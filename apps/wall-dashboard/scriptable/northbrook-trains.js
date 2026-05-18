// Northbrook Trains — Scriptable iOS home-screen widget.
//
// Setup:
//   1. Install the free "Scriptable" app from the App Store.
//   2. Scriptable → + → paste this whole file → name it "Northbrook Trains".
//   3. Set EXEC_URL below to your deployed Apps Script /exec URL.
//   4. Long-press the home screen → add a "Scriptable" widget → choose this
//      script. Small and Medium sizes are both supported.
//
// The widget reads the dashboard's JSON route (?view=trains&format=json):
//   { location, trains: [{ type, time, countdown_min, countdown_str }], updated_at }
//
// Design note: this is a first cut — colors, fonts, and spacing are meant to
// be tweaked. Edit the COLORS / Font calls below to taste.

const EXEC_URL = "PASTE_YOUR_APPS_SCRIPT_EXEC_URL_HERE";

// OLED-friendly dark palette, matching the TV dashboard.
const COLORS = {
  bg: new Color("#0a0a0a"),
  title: new Color("#9a9a9a"),
  primary: new Color("#e0e0e0"),
  accent: new Color("#7ab8ff"),
  countdown: new Color("#9a9a9a"),
  muted: new Color("#6a6a6a")
};

async function fetchTrains() {
  const req = new Request(EXEC_URL + "?view=trains&format=json");
  req.timeoutInterval = 15;
  return await req.loadJSON();
}

function header(widget, locationName) {
  const t = widget.addText((locationName || "Northbrook").toUpperCase());
  t.font = Font.semiboldSystemFont(12);
  t.textColor = COLORS.title;
}

function trainRow(widget, train) {
  const row = widget.addStack();
  row.centerAlignContent();

  const type = row.addText(train.type + "  ");
  type.font = Font.mediumSystemFont(16);
  type.textColor = COLORS.accent;

  const time = row.addText(train.time || "");
  time.font = Font.mediumSystemFont(16);
  time.textColor = COLORS.primary;

  row.addSpacer();

  const cd = row.addText(train.countdown_str || "");
  cd.font = Font.systemFont(14);
  cd.textColor = COLORS.countdown;
}

function buildWidget(data) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(14, 16, 14, 16);

  header(w, data && data.location);
  w.addSpacer(9);

  const trains = (data && data.trains) || [];
  if (trains.length === 0) {
    const empty = w.addText("No upcoming trains");
    empty.font = Font.systemFont(15);
    empty.textColor = COLORS.muted;
  } else {
    // A small widget has room for ~2 rows; medium/large for 3.
    const limit = config.widgetFamily === "small" ? 2 : 3;
    trains.slice(0, limit).forEach(function (train, i) {
      if (i > 0) w.addSpacer(8);
      trainRow(w, train);
    });
  }

  w.addSpacer();
  const upd = w.addText("Updated " + ((data && data.updated_at) || "—"));
  upd.font = Font.systemFont(10);
  upd.textColor = COLORS.muted;
  return w;
}

function messageWidget(message) {
  const w = new ListWidget();
  w.backgroundColor = COLORS.bg;
  w.setPadding(14, 16, 14, 16);
  header(w, "Northbrook");
  w.addSpacer(9);
  const m = w.addText(message);
  m.font = Font.systemFont(14);
  m.textColor = COLORS.muted;
  return w;
}

let widget;
try {
  if (EXEC_URL.indexOf("PASTE_") === 0) {
    widget = messageWidget("Set EXEC_URL in the script");
  } else {
    widget = buildWidget(await fetchTrains());
  }
} catch (e) {
  widget = messageWidget("Couldn't load trains");
}

if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentMedium();
}
Script.complete();
