# Wall Dashboard

Wall-mounted TV dashboard (Glenview weather + Northbrook trains) built as a
Google Apps Script web app.

## One-time setup

1. **Create the Sheet.** Follow `docs/sheet-setup.md` — make the Sheet and its
   `Config` and `AmtrakSchedule` tabs.
2. **Open the script editor.** In the Sheet: Extensions → Apps Script.
3. **Add the files.** In the editor, recreate each file from `apps-script/`:
   - `Code.gs` — paste over the default `Code.gs`.
   - `Dashboard.html` — File → New → HTML, name it `Dashboard`, paste.
   - `appsscript.json` — Project Settings → check "Show appsscript.json", then
     paste its contents over the manifest.
4. **Deploy.** Deploy → New deployment → type **Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone**
   - Click Deploy, authorize when prompted, copy the `/exec` URL.
   - **Record the deployment ID** — always reuse it for future updates so the
     Fire Stick bookmark never breaks.

## Updating later

Edit files in the editor, then Deploy → Manage deployments → edit the existing
deployment → New version. The `/exec` URL stays the same.

## Fire Stick

Install **Fully Kiosk Browser**, set the start URL to the `/exec` URL, enable
kiosk mode and auto-launch on boot.

## Tests

Pure logic is unit-tested with Node (no dependencies):

    cd apps/wall-dashboard
    node tests/pure-logic.test.js
