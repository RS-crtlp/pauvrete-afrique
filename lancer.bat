@echo off
cd /d "%~dp0"
start "" http://localhost:8000
python serveur.py --port 8000 --heures 6
