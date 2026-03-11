@echo off
REM Cronos - Atalho de execução para Windows
REM Clique duplo para executar ou execute via cmd

cd /d "%~dp0"

REM Tenta ambiente virtual primeiro
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe cronos.py
) else (
    python cronos.py
)

REM Se houve erro, pausa para mostrar mensagem
if errorlevel 1 (
    echo.
    echo Erro ao iniciar o Cronos.
    echo Consulte a DOCUMENTACAO.txt para instrucoes de instalacao.
    pause
)
