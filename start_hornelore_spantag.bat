@echo off
setlocal

REM ============================================================
REM SPANTAG-ON variant of start_hornelore.bat
REM ------------------------------------------------------------
REM Flips .env from HORNELORE_SPANTAG=0 to =1 BEFORE launching,
REM so common.sh sources the new value into the server env.
REM
REM Pair with stop_hornelore_spantag.bat to flip back to =0
REM after the bench. Default-off discipline must be restored.
REM ============================================================

set HORNELORE_REPO=/mnt/c/Users/chris/hornelore

echo.
echo [SPANTAG-ON] Flipping .env: HORNELORE_SPANTAG=0 -^> 1
wsl bash -lc "sed -i 's/^HORNELORE_SPANTAG=0/HORNELORE_SPANTAG=1/' %HORNELORE_REPO%/.env && echo '  Verified:' && grep '^HORNELORE_SPANTAG\|^SPANTAG_PASS' %HORNELORE_REPO%/.env"
echo.
echo [SPANTAG-ON] Launching stack. Server will inherit SPANTAG=1 via common.sh.
echo [SPANTAG-ON] WAIT FOUR FULL MINUTES for cold boot before benching.
echo [SPANTAG-ON] When done, click "Stop Hornelore SPANTAG OFF" to restore default.
echo.

where wt >nul 2>nul
if errorlevel 1 goto :fallback

wt ^
  new-tab --title "Hornelore API SPANTAG-ON" wsl.exe bash --login %HORNELORE_REPO%/scripts/start_api_visible.sh ; ^
  new-tab --title "Hornelore TTS" wsl.exe bash --login %HORNELORE_REPO%/scripts/start_tts_visible.sh ; ^
  new-tab --title "Hornelore UI"  wsl.exe bash --login %HORNELORE_REPO%/scripts/start_ui_visible.sh ; ^
  new-tab --title "Hornelore Logs" wsl.exe bash --login %HORNELORE_REPO%/scripts/logs_visible.sh

goto :done

:fallback
echo Windows Terminal not found - falling back to shell-native launcher.
wsl bash -lc "cd %HORNELORE_REPO% && bash scripts/start_all.sh"
pause

:done
endlocal
exit /b 0
