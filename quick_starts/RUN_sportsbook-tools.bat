@echo off
:: iOS App — no local server. Opens project folder + SETUP.md
cd /d "%~dp0..\shipped\sportsbook-tools"
start "" "SETUP.md"
explorer .
