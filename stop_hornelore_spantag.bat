@echo off
setlocal

REM ============================================================
REM SPANTAG-OFF variant of stop_hornelore.bat
REM ------------------------------------------------------------
REM Stops the stack, then flips .env back to HORNELORE_SPANTAG=0
REM to restore the default-off discipline locked by the
REM 2026-04-27 r5f-spantag-on-v3 rejection.
REM ============================================================

set HORNELORE_REPO=/mnt/c/Users/chris/hornelore

echo.
echo [SPANTAG-OFF] Stopping stack...
wsl bash %HORNELORE_REPO%/scripts/stop_all.sh

echo.
echo [SPANTAG-OFF] Flipping .env: HORNELORE_SPANTAG=1 -^> 0
wsl bash -lc "sed -i 's/^HORNELORE_SPANTAG=1/HORNELORE_SPANTAG=0/' %HORNELORE_REPO%/.env && echo '  Verified:' && grep '^HORNELORE_SPANTAG' %HORNELORE_REPO%/.env"

echo.
echo [SPANTAG-OFF] Done. .env is back to default-off state.
echo [SPANTAG-OFF] Next normal "Start Hornelore" will run SPANTAG=0.
pause

endlocal
exit /b 0
