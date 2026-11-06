"""
Тесты автоматического восстановления зомби-генераций при старте Django (CoreConfig.ready()).

Проверяем:
- _repair_stuck_on_startup исправляет старые processing → failed
- свежие processing не трогаются
- таймауты согласованы: FRONTEND_POLL_TIMEOUT_MS > SCREENSHOT_ZOMBIE_TIMEOUT * 1000
- ready() вызывает очистку при RUN_MAIN=true
- ready() не вызывает очистку при RUN_MAIN=false
- ready() не вызывает очистку при запуске pytest
"""
import sys
import os
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.utils import timezone

from core.constants import (
    SCREENSHOT_ZOMBIE_TIMEOUT,
    SCREENSHOT_WATCHDOG_TIMEOUT,
    FRONTEND_POLL_TIMEOUT_MS,
)
from core.models import Generation
from core.apps import CoreConfig, _repair_stuck_on_startup, _is_pytest


# ---------------------------------------------------------------------------
# Тесты согласованности таймаутов (без БД)
# ---------------------------------------------------------------------------

def test_timeout_constants_are_consistent():
    """FRONTEND_POLL_TIMEOUT_MS должен быть больше SCREENSHOT_ZOMBIE_TIMEOUT (в мс)."""
    zombie_ms = SCREENSHOT_ZOMBIE_TIMEOUT * 1000
    assert FRONTEND_POLL_TIMEOUT_MS > zombie_ms, (
        f"FRONTEND_POLL_TIMEOUT_MS ({FRONTEND_POLL_TIMEOUT_MS}) "
        f"должен быть > SCREENSHOT_ZOMBIE_TIMEOUT*1000 ({zombie_ms})"
    )


def test_timeout_order():
    """Порядок: WATCHDOG < ZOMBIE < FRONTEND (в секундах/мс соответственно)."""
    assert SCREENSHOT_WATCHDOG_TIMEOUT < SCREENSHOT_ZOMBIE_TIMEOUT
    assert SCREENSHOT_ZOMBIE_TIMEOUT * 1000 < FRONTEND_POLL_TIMEOUT_MS


# ---------------------------------------------------------------------------
# Тесты _is_pytest()
# ---------------------------------------------------------------------------

def test_is_pytest_returns_true_during_pytest():
    """_is_pytest() возвращает True, пока мы внутри pytest."""
    assert _is_pytest() is True


def test_is_pytest_returns_false_without_pytest():
    """_is_pytest() возвращает False, если pytest не загружен."""
    original = sys.modules.get('pytest')
    try:
        sys.modules.pop('pytest', None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('PYTEST_CURRENT_TEST', None)
            # Импортируем функцию заново, чтобы проверить логику без pytest в sys.modules
            import importlib
            import core.apps as apps_module
            importlib.reload(apps_module)
            # После reload pytest снова нет в sys.modules (мы его вынули)
            result = apps_module._is_pytest()
    finally:
        if original is not None:
            sys.modules['pytest'] = original
    # pytest уже убран из sys.modules и PYTEST_CURRENT_TEST не установлен → False
    assert result is False


# ---------------------------------------------------------------------------
# Тесты CoreConfig.ready() — мокируем _repair_stuck_on_startup
# ---------------------------------------------------------------------------

def _get_core_config():
    """Возвращает реальный экземпляр CoreConfig из реестра Django."""
    from django.apps import apps as django_apps
    return django_apps.get_app_config('core')


def test_ready_calls_repair_when_run_main_true():
    """ready() вызывает очистку, если RUN_MAIN=true (рабочий процесс runserver)."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, {'RUN_MAIN': 'true'}):
        cfg.ready()
    mock_repair.assert_called_once()


def test_ready_skips_repair_when_run_main_false():
    """ready() не вызывает очистку в родительском процессе авторелоадера (RUN_MAIN=false)."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, {'RUN_MAIN': 'false'}):
        cfg.ready()
    mock_repair.assert_not_called()


def test_ready_skips_repair_during_pytest():
    """ready() не вызывает очистку при запуске pytest."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=True), \
         patch.dict(os.environ, {'RUN_MAIN': 'true'}):
        cfg.ready()
    mock_repair.assert_not_called()


def test_ready_calls_repair_in_production_no_run_main():
    """ready() вызывает очистку в production (RUN_MAIN не установлен, pytest=False)."""
    cfg = _get_core_config()
    env_without_run_main = {k: v for k, v in os.environ.items() if k != 'RUN_MAIN'}
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, env_without_run_main, clear=True):
        cfg.ready()
    mock_repair.assert_called_once()


# ---------------------------------------------------------------------------
# Тесты _is_management_command() и защиты от management-команд
# ---------------------------------------------------------------------------

def test_is_management_command_repair():
    """repair_stuck_generations распознаётся как управляющая команда."""
    from core.apps import _is_management_command
    with patch.object(sys, 'argv', ['manage.py', 'repair_stuck_generations', '--dry-run']):
        assert _is_management_command() is True


def test_is_management_command_check():
    """check распознаётся как управляющая команда."""
    from core.apps import _is_management_command
    with patch.object(sys, 'argv', ['manage.py', 'check']):
        assert _is_management_command() is True


def test_is_management_command_runserver():
    """runserver НЕ в skip-списке — не считается управляющей командой."""
    from core.apps import _is_management_command
    with patch.object(sys, 'argv', ['manage.py', 'runserver', '0.0.0.0:8000']):
        assert _is_management_command() is False


def test_ready_skips_repair_for_repair_stuck_command():
    """ready() не вызывает очистку при manage.py repair_stuck_generations --dry-run."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, {'RUN_MAIN': 'true'}), \
         patch.object(sys, 'argv', ['manage.py', 'repair_stuck_generations', '--dry-run']):
        cfg.ready()
    mock_repair.assert_not_called()


def test_ready_skips_repair_for_check_command():
    """ready() не вызывает очистку при manage.py check."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, {'RUN_MAIN': 'true'}), \
         patch.object(sys, 'argv', ['manage.py', 'check']):
        cfg.ready()
    mock_repair.assert_not_called()


def test_ready_calls_repair_for_runserver():
    """ready() вызывает очистку при manage.py runserver с RUN_MAIN=true."""
    cfg = _get_core_config()
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, {'RUN_MAIN': 'true'}), \
         patch.object(sys, 'argv', ['manage.py', 'runserver']):
        cfg.ready()
    mock_repair.assert_called_once()


def test_ready_skips_repair_for_runserver_without_run_main():
    """ready() НЕ вызывает очистку при manage.py runserver без RUN_MAIN (родительский процесс)."""
    cfg = _get_core_config()
    env_without_run_main = {k: v for k, v in os.environ.items() if k != 'RUN_MAIN'}
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, env_without_run_main, clear=True), \
         patch.object(sys, 'argv', ['manage.py', 'runserver']):
        cfg.ready()
    mock_repair.assert_not_called()


def test_ready_calls_repair_production_no_argv():
    """ready() вызывает очистку в production (gunicorn/uWSGI — sys.argv без manage.py)."""
    cfg = _get_core_config()
    env_without_run_main = {k: v for k, v in os.environ.items() if k != 'RUN_MAIN'}
    with patch('core.apps._repair_stuck_on_startup') as mock_repair, \
         patch('core.apps._is_pytest', return_value=False), \
         patch.dict(os.environ, env_without_run_main, clear=True), \
         patch.object(sys, 'argv', ['gunicorn', 'config.wsgi']):
        cfg.ready()
    mock_repair.assert_called_once()


# ---------------------------------------------------------------------------
# Тесты _repair_stuck_on_startup с реальной БД
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_repair_stuck_on_startup_fixes_old():
    """_repair_stuck_on_startup переводит старую processing → failed."""
    gen = Generation.objects.create(status='processing')
    Generation.objects.filter(pk=gen.pk).update(
        created_at=timezone.now() - timedelta(seconds=SCREENSHOT_ZOMBIE_TIMEOUT + 60)
    )
    try:
        _repair_stuck_on_startup()
        gen.refresh_from_db()
        assert gen.status == 'failed'
        assert gen.completed_at is not None
        assert gen.duration_seconds is not None
        assert 'Зависание' in gen.error_message
    finally:
        Generation.objects.filter(pk=gen.pk).delete()


@pytest.mark.django_db
def test_repair_stuck_on_startup_ignores_fresh():
    """_repair_stuck_on_startup не трогает свежую processing-генерацию."""
    gen = Generation.objects.create(status='processing')
    try:
        _repair_stuck_on_startup()
        gen.refresh_from_db()
        assert gen.status == 'processing'
    finally:
        Generation.objects.filter(pk=gen.pk).delete()


@pytest.mark.django_db
def test_repair_stuck_on_startup_ignores_completed():
    """_repair_stuck_on_startup не трогает завершённые генерации."""
    gen = Generation.objects.create(status='completed')
    Generation.objects.filter(pk=gen.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    try:
        _repair_stuck_on_startup()
        gen.refresh_from_db()
        assert gen.status == 'completed'
    finally:
        Generation.objects.filter(pk=gen.pk).delete()
