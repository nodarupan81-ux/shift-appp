@echo off
cd /d C:\Users\noda\Desktop\my_project

REM 仮想環境を有効化
call .venv\Scripts\activate.bat

REM （少し待ってから）ブラウザで自動オープン
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5000

REM Flask アプリ起動
python app.py

pause
