@echo off
rem Resolves its own location - the repo can live anywhere.
setlocal
python "%~dp0bin\pipeline.py" %*
