@echo off
setlocal EnableDelayedExpansion
title Sudharshan AI — Trusted Code Signing Certificate Installer

echo ======================================================================
echo   Sudharshan AI (Alpha v0.9) — Windows Trusted Certificate Setup
echo ======================================================================
echo.

:: Detect Certificate path
set "CERT_FILE=%~dp0certificates\Sudharshan_AI_CodeSigning.cer"
if not exist "%CERT_FILE%" set "CERT_FILE=%~dp0Sudharshan_AI_CodeSigning.cer"

if not exist "%CERT_FILE%" (
    echo [ERROR] Certificate file (Sudharshan_AI_CodeSigning.cer) was not found!
    echo Looking in: %CERT_FILE%
    pause
    exit /b 1
)

echo [1/2] Installing Certificate to Windows Trusted Root Store...
certutil.exe -addstore -f "Root" "%CERT_FILE%"
if %ERRORLEVEL% neq 0 (
    echo [NOTICE] If prompt requested administrator elevation, please confirm to install.
)

echo.
echo [2/2] Installing Certificate to Windows Trusted Publishers Store...
certutil.exe -addstore -f "TrustedPublisher" "%CERT_FILE%"

echo.
echo ======================================================================
echo   SUCCESS! Sudharshan AI Desktop Authority is now a Trusted Publisher.
echo   Windows SmartScreen and Microsoft Defender will trust all
echo   Sudharshan AI applications and installers without security warnings.
echo ======================================================================
echo.
pause
