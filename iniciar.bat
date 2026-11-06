@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Concilia AI
if not exist ".venv\Scripts\python.exe" (
  echo Preparando a Concilia AI pela primeira vez. Isso leva alguns minutos...
  py -3 -m venv .venv || (echo Instale o Python 3.11 ou mais novo em python.org e tente de novo. & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo Falha ao instalar as bibliotecas. Verifique a internet. & pause & exit /b 1)
)
if not exist "exemplos\lote-misturado-horizonte.pdf" ".venv\Scripts\python.exe" ferramentas\gerar_exemplo.py
echo.
echo  Concilia AI rodando em http://127.0.0.1:8000
echo  Para parar, feche esta janela.
echo.
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
