# Wall Dashboard

A wall-mounted TV dashboard — Glenview weather, air quality, and the next
Northbrook trains (Amtrak + Metra) — plus a phone view and an iOS widget.
Built as a Google Apps Script web app.

## One-time setup

1. **Create the Sheet.** Follow `docs/sheet-setup.md` to make the Google Sheet
   and its `Config` tab. (The `AmtrakSchedule` tab is created automatically in
   step 5.)

2. **Open the script editor.** In the Sheet: Extensions -> Apps Script.

3. **Add the four files.** Recreate each file from `apps-script/`:
   - `Code.gs` -- paste over the default `Code.gs`.
   - `Dashboard.html` -- File -> New -> HTML, name it exactly `Dashboard`, paste.
   - `Trains.html` -- File -> New -> HTML, name it exactly `Trains`, paste.
   - `appsscript.json` -- Project Settings -> check "Show appsscript.json", paste.

4. **Deploy.** Deploy -> New deployment -> Web app. Execute as **Me**, access
   **Anyone**. Deploy, authorize, copy the `/exec` URL. **Record the deployment
   ID** -- reuse it for every future update so the Fire Stick URL never breaks.

5. **Run the one-time setup functions.** In the editor, pick each from the
   function dropdown and click Run (authorize when prompted):
   - `bootstrapNwsUrl` -- resolves and stores the NWS forecast URL. *Without
     this, the weather panel stays blank.*
   - `refreshAmtrakSchedule` -- pulls the Amtrak schedule into the
     `AmtrakSchedule` tab. *Without this, no Amtrak trains appear.*
   - `installAmtrakTrigger` -- installs the weekly Amtrak auto-refresh.

6. **Add the Metra token.** In the Sheet's `Config` tab, paste your Metra GTFS
   API token into the `metra_api_token` cell. *Without this, no Metra trains
   appear* (weather, AQI, and Amtrak still work without it).

## Views

- `<exec-url>` -- the TV dashboard.
- `<exec-url>?view=trains` -- a compact phone web view of the trains.
- `<exec-url>?view=trains&format=json` -- JSON, consumed by the iOS widget
  (`scriptable/northbrook-trains.js`).

## Updating later

Edit files in the editor, then Deploy -> Manage deployments -> edit the
existing deployment -> New version. The `/exec` URL stays the same.

## Fire Stick

Install **Fully Kiosk Browser**, set the start URL to the `/exec` URL, enable
kiosk mode and auto-launch on boot.

## Tests

Pure logic is unit-tested with Node (no dependencies):

    cd apps/wall-dashboard
    node tests/pure-logic.test.js
