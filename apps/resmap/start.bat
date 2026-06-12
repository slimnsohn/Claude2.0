@echo off
rem ResMap — opens the FAQ/explainer page. The data pipeline runs via
rem `python -m ingest.run` etc. (see README.md); this is the browser entry point.
start "" "%~dp0tool\web\faq.html"
