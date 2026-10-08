@echo off
chcp 65001 >nul
title Atualizar Jarvis
rem Baixa a versao mais nova do GitHub e copia por cima (o .env e a memoria ficam).
set RAMO=claude/new-session-x7a5cc
set DESTINO=%USERPROFILE%\assistente-pessoal
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $z=Join-Path $env:TEMP 'jarvis.zip'; $d=Join-Path $env:TEMP 'jarvis'; if(Test-Path $d){Remove-Item $d -Recurse -Force}; Invoke-WebRequest 'https://github.com/Ricardoem22/estoque.com/archive/refs/heads/%RAMO%.zip' -OutFile $z -UseBasicParsing; Expand-Archive $z $d -Force; $src=(Get-ChildItem $d | Select-Object -First 1).FullName; New-Item -ItemType Directory -Force '%DESTINO%' | Out-Null; Copy-Item (Join-Path $src 'assistente\*') '%DESTINO%' -Recurse -Force -Exclude 'Atualizar Jarvis.bat'; $v=(Select-String -Path '%DESTINO%\assistente.py' -Pattern 'VERSAO = .(\d+).').Matches[0].Groups[1].Value; Write-Host ('Arquivos atualizados. Versao instalada: ' + $v)"
if errorlevel 1 (
  echo Nao consegui atualizar. Verifique a internet.
  pause
  exit /b
)
python -m pip install -q -r "%DESTINO%\requirements.txt"
echo Pronto! Pode abrir o Jarvis.
pause
