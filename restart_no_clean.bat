@echo off
REM Restart Hornelore WITHOUT clearing browser state.
REM Keeps the open narrator, current era, and any unsaved questionnaire
REM draft. Touches no data; see scripts/restart_no_clean.sh for why.
setlocal

set HORNELORE_REPO=/mnt/c/Users/chris/hornelore

where wt >nul 2>nul
if errorlevel 1 goto :fallback

REM Stop first, in one window, then hand the services their own tabs —
REM the same shape "Start Hornelore.bat" uses, so the visible layout a
REM restart leaves behind matches the one a cold start does.
wsl bash -lc "cd %HORNELORE_REPO% && bash scripts/stop_all.sh --no-clean && rm -f .runtime/reset_on_start"

wt ^
  new-tab --title "Hornelore API" wsl.exe bash --login %HORNELORE_REPO%/scripts/start_api_visible.sh ; ^
  new-tab --title "Hornelore TTS" wsl.exe bash --login %HORNELORE_REPO%/scripts/start_tts_visible.sh ; ^
  new-tab --title "Hornelore UI"  wsl.exe bash --login %HORNELORE_REPO%/scripts/start_ui_visible.sh ; ^
  new-tab --title "Hornelore Logs" wsl.exe bash --login %HORNELORE_REPO%/scripts/logs_visible.sh

goto :done

:fallback
echo Windows Terminal not found - falling back to shell-native launcher.
wsl bash -lc "cd %HORNELORE_REPO% && bash scripts/restart_no_clean.sh"
pause

:done
endlocal
exit /b 0
