"""
Тесты защитного таймаута (watchdog) генерации.

Проверяют:
- После срабатывания watchdog статус = 'failed' (не 'processing', не 'completed')
- error_message содержит причину таймаута
- Повторный вызов для уже завершённой генерации ничего не меняет
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.views import _force_complete_generation
from core.models import Generation


def _make_mock_generation(status='processing'):
    """Создаёт мок Generation с нужными полями."""
    gen = MagicMock(spec=Generation)
    gen.status = status
    gen.created_at = MagicMock()
    gen.created_at.__class__ = object  # не datetime, заменим ниже
    gen.error_message = ''
    gen.completed_at = None
    gen.duration_seconds = None
    return gen


# ── Тест W1: watchdog → failed, не completed ──────────────────────────

def test_watchdog_sets_failed_status():
    """После срабатывания таймаута статус = 'failed', а не 'completed' или 'processing'."""
    from django.utils import timezone
    gen = MagicMock()
    gen.status = 'processing'
    gen.created_at = timezone.now()

    with patch('core.views.Generation.objects') as mock_objects, \
         patch('core.views._save_experiment_result_safe') as mock_save, \
         patch('django.db.close_old_connections'):
        mock_objects.get.return_value = gen
        _force_complete_generation(999, "защитный таймаут 900с истёк")

    assert gen.status == 'failed', f"Ожидали 'failed', получили '{gen.status}'"
    assert 'таймаут' in gen.error_message.lower(), f"error_message должен содержать 'таймаут': {gen.error_message}"
    gen.save.assert_called_once()
    mock_save.assert_called_once_with(gen)
    print(f"  PASS test_watchdog_sets_failed_status: status={gen.status!r}, msg={gen.error_message!r}")


def test_watchdog_does_not_override_completed():
    """Если генерация уже completed — watchdog ничего не меняет."""
    gen = MagicMock()
    gen.status = 'completed'

    with patch('core.views.Generation.objects') as mock_objects, \
         patch('core.views._save_experiment_result_safe') as mock_save, \
         patch('django.db.close_old_connections'):
        mock_objects.get.return_value = gen
        _force_complete_generation(999, "таймаут")

    assert gen.status == 'completed', "Уже completed — не должен меняться"
    gen.save.assert_not_called()
    mock_save.assert_not_called()
    print(f"  PASS test_watchdog_does_not_override_completed")


def test_watchdog_does_not_override_failed():
    """Если генерация уже failed — watchdog ничего не меняет."""
    gen = MagicMock()
    gen.status = 'failed'

    with patch('core.views.Generation.objects') as mock_objects, \
         patch('core.views._save_experiment_result_safe') as mock_save, \
         patch('django.db.close_old_connections'):
        mock_objects.get.return_value = gen
        _force_complete_generation(999, "таймаут")

    assert gen.status == 'failed'
    gen.save.assert_not_called()
    print(f"  PASS test_watchdog_does_not_override_failed")


def test_watchdog_error_message_contains_reason():
    """error_message содержит переданную причину таймаута."""
    from django.utils import timezone
    gen = MagicMock()
    gen.status = 'processing'
    gen.created_at = timezone.now()

    reason = "защитный таймаут 900с истёк"
    with patch('core.views.Generation.objects') as mock_objects, \
         patch('core.views._save_experiment_result_safe'), \
         patch('django.db.close_old_connections'):
        mock_objects.get.return_value = gen
        _force_complete_generation(999, reason)

    assert reason in gen.error_message, f"Причина должна быть в error_message: {gen.error_message!r}"
    print(f"  PASS test_watchdog_error_message_contains_reason: {gen.error_message!r}")


def test_watchdog_handles_db_exception_gracefully():
    """При ошибке БД watchdog не падает с необработанным исключением."""
    with patch('core.views.Generation.objects') as mock_objects, \
         patch('django.db.close_old_connections'):
        mock_objects.get.side_effect = Exception("БД недоступна")
        try:
            _force_complete_generation(999, "таймаут")
        except Exception as e:
            assert False, f"watchdog должен перехватывать исключения: {e}"
    print(f"  PASS test_watchdog_handles_db_exception_gracefully")


# ── Runner ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_watchdog_sets_failed_status,
        test_watchdog_does_not_override_completed,
        test_watchdog_does_not_override_failed,
        test_watchdog_error_message_contains_reason,
        test_watchdog_handles_db_exception_gracefully,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("Watchdog таймаут — тесты")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}\n")

    import sys
    sys.exit(0 if failed == 0 else 1)
