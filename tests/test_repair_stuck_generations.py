"""
Тесты management-команды repair_stuck_generations.

Проверяем:
- dry-run: ничего не меняет в БД
- реальный запуск: старые processing → failed с заполненными полями
- свежие processing не трогаются
- уже завершённые генерации не трогаются
- --timeout переопределяет порог
"""
import sys
import os
from pathlib import Path
from datetime import timedelta
from io import StringIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.utils import timezone
from django.core.management import call_command

from core.models import Generation


def _make_gen(status='processing', minutes_ago=25, project_id=1):
    """Создаёт реальную запись Generation в тестовой БД."""
    gen = Generation.objects.create(
        status=status,
        project_id=project_id,
    )
    # Сдвигаем created_at назад через прямой UPDATE чтобы не упираться в auto_now_add
    Generation.objects.filter(pk=gen.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes_ago)
    )
    gen.refresh_from_db()
    return gen


def _cleanup(*pks):
    Generation.objects.filter(pk__in=pks).delete()


@pytest.mark.django_db
def test_repair_fixes_old_stuck_generation():
    """Старая processing-генерация (25 мин) → failed после команды."""
    gen = _make_gen(status='processing', minutes_ago=25)
    try:
        call_command('repair_stuck_generations', timeout=20, stdout=StringIO(), stderr=StringIO())
        gen.refresh_from_db()
        assert gen.status == 'failed', f"Ожидался failed, получен {gen.status!r}"
        assert gen.completed_at is not None, "completed_at должен быть заполнен"
        assert gen.duration_seconds is not None, "duration_seconds должен быть заполнен"
        assert 'Таймаут' in gen.error_message or 'таймаут' in gen.error_message.lower(), \
            f"error_message должен содержать 'Таймаут': {gen.error_message!r}"
    finally:
        _cleanup(gen.pk)
    print("  PASS test_repair_fixes_old_stuck_generation")


@pytest.mark.django_db
def test_repair_dry_run_does_not_change_db():
    """--dry-run: статус остаётся processing, БД не меняется."""
    gen = _make_gen(status='processing', minutes_ago=25)
    try:
        call_command('repair_stuck_generations', timeout=20, dry_run=True,
                     stdout=StringIO(), stderr=StringIO())
        gen.refresh_from_db()
        assert gen.status == 'processing', \
            f"dry-run не должен менять статус, получен {gen.status!r}"
        assert gen.completed_at is None, "dry-run не должен заполнять completed_at"
    finally:
        _cleanup(gen.pk)
    print("  PASS test_repair_dry_run_does_not_change_db")


@pytest.mark.django_db
def test_repair_ignores_fresh_generation():
    """Свежая processing-генерация (5 мин) не затрагивается."""
    gen = _make_gen(status='processing', minutes_ago=5)
    try:
        call_command('repair_stuck_generations', timeout=20, stdout=StringIO(), stderr=StringIO())
        gen.refresh_from_db()
        assert gen.status == 'processing', \
            f"Свежая генерация не должна меняться, получен {gen.status!r}"
    finally:
        _cleanup(gen.pk)
    print("  PASS test_repair_ignores_fresh_generation")


@pytest.mark.django_db
def test_repair_ignores_completed_generation():
    """completed-генерация не затрагивается независимо от возраста."""
    gen = _make_gen(status='completed', minutes_ago=60)
    try:
        call_command('repair_stuck_generations', timeout=20, stdout=StringIO(), stderr=StringIO())
        gen.refresh_from_db()
        assert gen.status == 'completed', \
            f"completed не должна меняться, получен {gen.status!r}"
    finally:
        _cleanup(gen.pk)
    print("  PASS test_repair_ignores_completed_generation")


@pytest.mark.django_db
def test_repair_custom_timeout():
    """--timeout 10: генерация 15 мин назад → failed."""
    gen = _make_gen(status='processing', minutes_ago=15)
    try:
        call_command('repair_stuck_generations', timeout=10, stdout=StringIO(), stderr=StringIO())
        gen.refresh_from_db()
        assert gen.status == 'failed', \
            f"С timeout=10 генерация 15 мин назад должна стать failed, получен {gen.status!r}"
    finally:
        _cleanup(gen.pk)
    print("  PASS test_repair_custom_timeout")


@pytest.mark.django_db
def test_repair_no_stuck_prints_success():
    """Если нет зависших генераций, команда не падает."""
    out = StringIO()
    call_command('repair_stuck_generations', timeout=20, stdout=out, stderr=StringIO())
    # Команда должна завершиться без исключений
    print("  PASS test_repair_no_stuck_prints_success")


if __name__ == '__main__':
    test_repair_fixes_old_stuck_generation()
    test_repair_dry_run_does_not_change_db()
    test_repair_ignores_fresh_generation()
    test_repair_ignores_completed_generation()
    test_repair_custom_timeout()
    test_repair_no_stuck_prints_success()
    print("\nВсе тесты repair_stuck_generations прошли.")
