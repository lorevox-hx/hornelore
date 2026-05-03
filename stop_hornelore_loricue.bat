@echo off
setlocal

REM ============================================================
REM LORI-CUE-OFF variant of stop_hornelore.bat
REM ------------------------------------------------------------
REM Stops the stack, then flips .env back to
REM HORNELORE_LORI_CUE_LOG=0 to restore the default-off
REM discipline. Same pattern as stop_hornelore_spantag.bat.
REM ============================================================

set HORNELORE_REPO=/mnt/c/Users/chris/hornelore

echo.
echo [LORI-CUE-OFF] Stopping stack...
wsl bash %HORNELORE_REPO%/scripts/stop_all.sh

echo.
echo [LORI-CUE-OFF] Flipping .env: HORNELORE_LORI_CUE_LOG=1 -^> 0
wsl bash -lc "sed -i 's/^HORNELORE_LORI_CUE_LOG=1/HORNELORE_LORI_CUE_LOG=0/' %HORNELORE_REPO%/.env && echo '  Verified:' && grep '^HORNELORE_LORI_CUE_LOG' %HORNELORE_REPO%/.env"

echo.
echo [LORI-CUE-OFF] Done. .env is back to default-off state.
echo [LORI-CUE-OFF] Next normal "Start Hornelore" will run LORI_CUE_LOG=0.
pause

endlocal
exit /b 0
