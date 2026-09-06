@echo off
cd /d "%~dp0"
py -3.10 probe_launcher.py
if errorlevel 1 (
  echo.
  echo Start fehlgeschlagen. Python 3.10 oder neuer mit Tkinter wird benoetigt.
  pause
)
