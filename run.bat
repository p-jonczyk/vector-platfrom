@echo off
title Raster Wektor
cd /d "%~dp0"

echo ============================================================
echo  Raster - Wektor  ^|  uruchamianie
echo ============================================================
echo.

:: ── 1. Git pull ──────────────────────────────────────────────
echo [1/4] Aktualizacja (git pull)...
git pull
if errorlevel 1 echo UWAGA: git pull nie powiodl sie. Uruchamiam obecna wersje.
echo.

:: ── 2. Venv ──────────────────────────────────────────────────
echo [2/4] Srodowisko Python...
if exist "venv\Scripts\activate.bat" goto :venv_ready

echo Tworzenie nowego venv py -3.14 ...
py -3.14 -m venv venv
if errorlevel 1 goto :venv_error

:venv_ready
call venv\Scripts\activate.bat
echo.

:: ── 3. Zaleznosci ────────────────────────────────────────────
echo [3/4] Instalacja/aktualizacja zaleznosci...
pip install -r requirements.txt -q
if errorlevel 1 goto :pip_error
echo.

:: ── 4. Uruchom aplikacje ─────────────────────────────────────
echo [4/4] Uruchamianie aplikacji...
echo  Adres: http://localhost:5000
echo  Zamknij to okno aby wylaczyc.
echo ============================================================
echo.
python app.py

echo.
echo Aplikacja zatrzymana.
pause
exit /b 0

:venv_error
echo BLAD: Nie mozna utworzyc venv. Sprawdz czy Python 3.14 jest zainstalowany.
pause
exit /b 1

:pip_error
echo BLAD: pip install nie powiodl sie.
pause
exit /b 1
