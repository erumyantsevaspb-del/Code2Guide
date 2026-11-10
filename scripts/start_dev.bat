@echo off
cd /d "%~dp0.."

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

if not exist logs mkdir logs

echo Запуск Code2Guide...
echo Логи: logs\django-dev.log
echo Остановить: Ctrl+C

python manage.py runserver --noreload 127.0.0.1:8000 >> logs\django-dev.log 2>&1
