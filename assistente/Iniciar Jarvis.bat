@echo off
chcp 65001 >nul
title Jarvis
cd /d "%USERPROFILE%\assistente-pessoal"
if errorlevel 1 (
  echo Nao encontrei a pasta %USERPROFILE%\assistente-pessoal
  pause
  exit /b
)
python assistente.py
pause
