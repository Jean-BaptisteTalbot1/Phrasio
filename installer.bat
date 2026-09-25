@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installation de Phrasio...
echo Cela peut prendre 5 a 10 minutes (environ 1 Go de librairies a telecharger).
where py >nul 2>nul || (echo Python introuvable. Installe-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH". & pause & exit /b 1)
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv || (echo Echec de creation de l'environnement. & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt -q || (echo Echec d'installation des librairies. & pause & exit /b 1)
echo.
echo Installation terminee. Lance Phrasio avec lancer.bat
pause
