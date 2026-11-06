@echo off
cd /d C:\Users\Lena\Code2Guide

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

if not exist logs mkdir logs

python manage.py repair_stuck_generations >> logs\repair_stuck_generations.log 2>&1
