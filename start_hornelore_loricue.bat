@echo off
setlocal

REM ============================================================
REM LORI-CUE-LOG variant of start_hornelore.bat
REM ------------------------------------------------------------
REM Flips .env from HORNELORE_LORI_CUE_LOG=0 to =1 BEFORE
REM launching, so common.sh sources the new value into the
REM server env. Same pattern as start_hornelore_spantag.bat.
REM
REM Pair with stop_hornelore_loricue.bat to flip back to =0
REM after the survey. Default-off discipline must be restored.
REM
REM Use case: turn this on for a session you want to survey,
REM then grep .runtime/logs/api.log for [lori-cue] to inspect
REM which cue types fire on real narrator-shaped text. Feed
REM observations back into library tuning via
REM scripts/run_narrative_cue_eval.py.
REM ============================================================

set HORNELORE_REPO=/mnt/c/Users/chris/hornelore

echo.
echo [LORI-CUE-LOG] Flipping .env: HORNELORE_LORI_CUE_LOG=0 -^> 1
wsl bash -lc "sed -i 's/^HORNELORE_LORI_CUE_LOG=0/HORNELORE_LORI_CUE_LOG=1/' %HORNELORE_REPO%/.env && echo '  Verified:' && grep '^HORNELORE_LORI_CUE_LOG' %HORNELORE_REPO%/.env"
echo.
echo [LORI-CUE-LOG] Launching stack. Server will inherit LORI_CUE_LOG=1 via common.sh.
echo [LORI-CUE-LOG] WAIT FOUR FULL MINUTES for cold boot before surveying.
echo [LORI-CUE-LOG] When done, click "Stop Hornelore LORI-CUE OFF" to restore default.
echo.

where wt >nul 2>nul
if errorlevel 1 goto :fallback

wt ^
  new-tab --title "Hornelore API LORI-CUE-LOG" wsl.exe bash --login %HORNELORE_REPO%/scripts/start_api_visible.sh ; ^
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
