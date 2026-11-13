@echo off
title Sudharshan AI — Unblock Downloaded Files

echo ======================================================================
echo   Sudharshan AI (Alpha v0.9) — Windows Download Security Unblocker
echo ======================================================================
echo.
echo Removing Windows browser Mark-of-the-Web (Zone.Identifier) locks...

powershell.exe -NoProfile -Command "Get-ChildItem -Path '%~dp0*' -Recurse | Unblock-File -ErrorAction SilentlyContinue"

echo.
echo ======================================================================
echo   SUCCESS! All downloaded Sudharshan AI files have been unblocked.
echo   You can now run setup_windows.bat or Sudharshan_AI_Setup.exe cleanly.
echo ======================================================================
echo.
pause
