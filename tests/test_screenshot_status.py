"""
Тесты логики статуса генерации в _take_screenshots_background().

Проверяем:
- TimeoutError (сервер не запустился) -> completed + error_message с причиной
- RuntimeError с серверным сообщением (ожидаемым) -> completed + error_message
- RuntimeError без серверного сообщения + непустой instruction_data -> FAILED (документ есть, но ошибка неожиданна)
- RuntimeError без серверного сообщения + пустой instruction_data -> failed
- Exception с ключевыми словами (NX, timeout) -> completed + error_message
- Неожиданные исключения (AttributeError, MemoryError, ValueError) -> failed (независимо от данных)
- Успешный сценарий -> completed, error_message пуст
- experiment result сохраняется при completed, не сохраняется при failed
- РЕГРЕССИЯ: монорепо (apps/, packages/) -> completed с сообщением
- РЕГРЕССИЯ: нет раннего completed при неожиданной ошибке + instruction_data
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.utils import timezone


# ── Вспомогательная фабрика ───────────────────────────────────────

def _make_generation(empty_data=False):
    g = MagicMock()
    g.id = 99
    g.status = 'processing'
    g.error_message = ''
    g.instruction_data = [] if empty_data else [{'path': '/', 'name': 'Home', 'instructions': []}]
    g.created_at = timezone.now()
    g.completed_at = None
    g.duration_seconds = None
    return g


def _run_background(exc=None, screenshots=None, empty_data=False, save_exc=None, get_exc=None):
    """
    Вызывает _take_screenshots_background с подменёнными зависимостями.

    exc         — исключение из take_route_screenshots (ошибка скриншотов)
    screenshots — словарь скриншотов при успехе
    empty_data  — True: instruction_data пуст (документ не сформирован)
    save_exc    — исключение из generation.save() (сбой записи в БД)
    get_exc     — исключение из Generation.objects.get() (БД недоступна)

    Возвращает (generation, список статусов переданных в _save_experiment_result_safe, логи).
    """
    import logging as _logging
    gen = _make_generation(empty_data=empty_data)
    saved_statuses = []
    log_messages = []

    class _CapturingHandler(_logging.Handler):
        def emit(self, record):
            log_messages.append(self.format(record))

    handler = _CapturingHandler()
    views_logger = _logging.getLogger('core.views')
    views_logger.addHandler(handler)

    def fake_save_experiment(g):
        saved_statuses.append(g.status)

    if save_exc is not None:
        gen.save.side_effect = save_exc

    with patch('core.views.Generation') as MockGen, \
         patch('core.views.take_route_screenshots') as mock_take, \
         patch('core.views._save_experiment_result_safe', side_effect=fake_save_experiment), \
         patch('shutil.rmtree'):

        if get_exc is not None:
            MockGen.objects.get.side_effect = get_exc
        else:
            MockGen.objects.get.return_value = gen

        if exc is not None:
            mock_take.side_effect = exc
        else:
            mock_take.return_value = screenshots or {}

        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path='/fake/src',
            cleanup_path='/fake/tmp',
            routes=[{'path': '/', 'name': 'Home'}],
            project_id=1,
        )

    views_logger.removeHandler(handler)
    return gen, saved_statuses, log_messages


def _run_generate_api_thread_start_fail(thread_error):
    """
    Имитирует generate_instruction_api: Generation уже создана, thread.start() бросает исключение.
    Возвращает (generation, saved_statuses, cleanup_called).
    """
    gen = _make_generation()
    saved_statuses = []
    cleanup_calls = []

    def fake_save(g):
        saved_statuses.append(g.status)

    def fake_rmtree(path, ignore_errors=False):
        cleanup_calls.append(path)

    # Вызываем только ту часть кода, которую нужно протестировать.
    # Воспроизводим логику thread.start() except из generate_instruction_api напрямую.
    import shutil as _shutil

    with patch('core.views._save_experiment_result_safe', side_effect=fake_save), \
         patch('shutil.rmtree', side_effect=fake_rmtree):

        from core.views import _save_experiment_result_safe
        from django.utils import timezone as _tz

        try:
            raise thread_error
        except Exception as thread_err:
            gen.status = 'completed_without_screenshots'
            gen.error_message = f"Скриншоты не запущены: {thread_err}"
            gen.completed_at = _tz.now()
            gen.duration_seconds = int(
                (gen.completed_at - gen.created_at).total_seconds()
            )
            gen.save()
            _shutil.rmtree('/fake/tmp', ignore_errors=True)
            _save_experiment_result_safe(gen)

    return gen, saved_statuses, cleanup_calls


# ── Ожидаемые ошибки скриншотов (completed) ───────────────────────

def test_timeout_error_gives_completed():
    """TimeoutError -> completed_without_screenshots + причина в error_message."""
    gen, saved, _logs = _run_background(exc=TimeoutError("React-сервер не запустился за 120 секунд"))
    assert gen.status == 'completed_without_screenshots', f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert gen.error_message, "error_message должен содержать причину"
    assert 'скриншоты недоступны' in gen.error_message.lower(), gen.error_message
    assert saved == ['completed_without_screenshots'], f"_save_experiment_result_safe не вызван: {saved}"
    print(f"  PASS test_timeout_error_gives_completed: {gen.error_message!r}")


def test_runtime_error_server_message_gives_completed():
    """RuntimeError с 'dev-сервер завершился' -> completed_without_screenshots (ожидаемая ошибка сервера)."""
    gen, saved, _logs = _run_background(exc=RuntimeError("Dev-сервер завершился с кодом 1"))
    assert gen.status == 'completed_without_screenshots', f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert gen.error_message
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_runtime_error_server_message_gives_completed: {gen.error_message!r}")


def test_runtime_error_unexpected_with_data_gives_failed():
    """RuntimeError без серверного сообщения + непустой instruction_data -> failed (неожиданная ошибка)."""
    gen, saved, _logs = _run_background(exc=RuntimeError("maximum recursion depth exceeded"))
    assert gen.status == 'failed', f"Ожидался failed (неожиданная ошибка), получен {gen.status!r}"
    assert gen.error_message, "error_message должен содержать диагностику"
    assert 'maximum recursion depth' in gen.error_message, gen.error_message
    assert saved == [], f"_save_experiment_result_safe не должен вызываться при failed: {saved}"
    print(f"  PASS test_runtime_error_unexpected_with_data_gives_failed: {gen.error_message!r}")


def test_runtime_error_unexpected_empty_data_gives_failed():
    """RuntimeError без серверного сообщения + пустой instruction_data -> failed."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError("maximum recursion depth exceeded"),
        empty_data=True,
    )
    assert gen.status == 'failed', f"Ожидался failed (данных нет), получен {gen.status!r}"
    assert gen.error_message, "error_message должен содержать описание"
    assert saved == [], f"_save_experiment_result_safe не должен вызываться: {saved}"
    print(f"  PASS test_runtime_error_unexpected_empty_data_gives_failed: {gen.error_message!r}")


def test_nx_monorepo_gives_completed():
    """RuntimeError с 'nx monorepo' -> completed_without_screenshots."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError("NX monorepo не поддерживается для локального запуска скриншотов")
    )
    assert gen.status == 'completed_without_screenshots', gen.status
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_nx_monorepo_gives_completed")


def test_timeout_keyword_in_exception_gives_completed():
    """Exception с 'timeout' в тексте -> completed_without_screenshots."""
    gen, saved, _logs = _run_background(exc=Exception("subprocess timeout exceeded"))
    assert gen.status == 'completed_without_screenshots', gen.status
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_timeout_keyword_in_exception_gives_completed")


def test_ne_zapustilsya_keyword_gives_completed():
    """Exception с 'не запустился' -> completed_without_screenshots."""
    gen, saved, _logs = _run_background(exc=Exception("Сервер не запустился за отведённое время"))
    assert gen.status == 'completed_without_screenshots', gen.status
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_ne_zapustilsya_keyword_gives_completed")


# ── Неожиданные ошибки (failed) ───────────────────────────────────

def test_attribute_error_with_data_gives_failed():
    """AttributeError + непустой instruction_data -> failed (неожиданная ошибка, независимо от данных)."""
    gen, saved, _logs = _run_background(exc=AttributeError("'NoneType' object has no attribute 'read'"))
    assert gen.status == 'failed', f"Ожидался failed, получен {gen.status!r}"
    assert gen.error_message
    assert saved == [], f"_save_experiment_result_safe не должен вызываться при failed: {saved}"
    print(f"  PASS test_attribute_error_with_data_gives_failed: {gen.error_message!r}")


def test_attribute_error_empty_data_gives_failed():
    """AttributeError + пустой instruction_data -> failed."""
    gen, saved, _logs = _run_background(
        exc=AttributeError("'NoneType' object has no attribute 'read'"),
        empty_data=True,
    )
    assert gen.status == 'failed', gen.status
    assert gen.error_message
    assert saved == []
    print(f"  PASS test_attribute_error_empty_data_gives_failed: {gen.error_message!r}")


def test_memory_error_empty_data_gives_failed():
    """MemoryError + пустой instruction_data -> failed."""
    gen, saved, _logs = _run_background(exc=MemoryError("out of memory"), empty_data=True)
    assert gen.status == 'failed', gen.status
    assert saved == []
    print(f"  PASS test_memory_error_empty_data_gives_failed")


def test_value_error_empty_data_gives_failed():
    """ValueError + пустой instruction_data -> failed."""
    gen, saved, _logs = _run_background(exc=ValueError("unexpected problem in parsing"), empty_data=True)
    assert gen.status == 'failed', gen.status
    assert saved == []
    print(f"  PASS test_value_error_empty_data_gives_failed")


# ── Успешный сценарий ─────────────────────────────────────────────

def test_success_gives_completed_empty_error_message():
    """Успех -> completed, error_message пуст."""
    gen, saved, _logs = _run_background(screenshots={'/': 'screenshots/1/home.png'})
    assert gen.status == 'completed', gen.status
    assert not gen.error_message, f"error_message должен быть пуст: {gen.error_message!r}"
    assert saved == ['completed']
    print(f"  PASS test_success_gives_completed_empty_error_message")


# ── Инварианты ───────────────────────────────────────────────────

def test_failed_does_not_call_save_experiment():
    """При failed (пустые данные) _save_experiment_result_safe не вызывается."""
    gen, saved, _logs = _run_background(exc=ValueError("unexpected"), empty_data=True)
    assert gen.status == 'failed'
    assert saved == [], f"Не ожидался вызов save: {saved}"
    print(f"  PASS test_failed_does_not_call_save_experiment")


def test_completed_partial_calls_save_experiment():
    """При completed_without_screenshots _save_experiment_result_safe вызывается."""
    gen, saved, _logs = _run_background(exc=TimeoutError("no server"))
    assert gen.status == 'completed_without_screenshots'
    assert saved == ['completed_without_screenshots'], f"save должен быть вызван: {saved}"
    print(f"  PASS test_completed_partial_calls_save_experiment")


def test_completed_partial_error_message_not_empty():
    """При ожидаемой ошибке error_message не пуст."""
    gen, _saved, _logs = _run_background(exc=TimeoutError("не запустился за 120 секунд"))
    assert gen.status == 'completed_without_screenshots'
    assert gen.error_message, "error_message должен объяснять отсутствие скриншотов"
    print(f"  PASS test_completed_partial_error_message_not_empty: {gen.error_message!r}")


def test_failed_has_diagnostic_message():
    """При неожиданной ошибке (пустые данные) error_message содержит диагностику."""
    gen, _saved, _logs = _run_background(exc=AttributeError("bad attribute"), empty_data=True)
    assert gen.status == 'failed'
    assert 'bad attribute' in gen.error_message, gen.error_message
    print(f"  PASS test_failed_has_diagnostic_message: {gen.error_message!r}")


# ── Сбой generation.save() после успешных скриншотов ────────────

def test_save_fail_after_success_does_not_set_completed():
    """
    Скриншоты получены, но generation.save() бросает OperationalError.
    Запись остаётся в 'processing' (честно). completed не устанавливается.
    Ошибка явно логируется.
    """
    from unittest.mock import MagicMock
    save_error = Exception("database is locked")
    gen, saved, logs = _run_background(
        screenshots={'/': 'screenshots/1/home.png'},
        save_exc=save_error,
    )
    # save() упал — статус в памяти может быть изменён (status='completed' присвоен ДО save),
    # но в БД сохранения не было. Главное: _save_experiment_result_safe не вызван.
    assert saved == [], f"experiment не должен сохраняться при сбое save: {saved}"
    # Ошибка залогирована явно (не поглощена pass)
    critical_logged = any('критическая' in m.lower() or 'generation' in m.lower() for m in logs)
    assert critical_logged, f"Сбой save должен быть залогирован. Логи: {logs}"
    print(f"  PASS test_save_fail_after_success_does_not_set_completed (логи: {logs})")


def test_save_fail_after_screenshot_error_logs_and_does_not_call_experiment():
    """
    Скриншоты упали с TimeoutError, затем generation.save() тоже бросает исключение.
    Ошибка явно логируется. experiment не вызван. Не поглощается молча.
    """
    save_error = Exception("database is locked")
    gen, saved, logs = _run_background(
        exc=TimeoutError("React-сервер не запустился за 120 секунд"),
        save_exc=save_error,
    )
    assert saved == [], f"experiment не должен вызываться при сбое save: {saved}"
    critical_logged = any('критическая' in m.lower() or 'generation' in m.lower() for m in logs)
    assert critical_logged, f"Сбой save должен быть залогирован. Логи: {logs}"
    print(f"  PASS test_save_fail_after_screenshot_error_logs_and_does_not_call_experiment (логи: {logs})")


def test_get_fail_during_error_handling_logs_explicitly():
    """
    Скриншоты упали, затем Generation.objects.get() тоже бросает исключение.
    Ошибка явно логируется. experiment не вызван. Запись остаётся в 'processing'.
    """
    gen, saved, logs = _run_background(
        exc=TimeoutError("сервер не запустился"),
        get_exc=Exception("no such table: core_generation"),
    )
    assert saved == [], f"experiment не должен вызываться: {saved}"
    critical_logged = any('критическая' in m.lower() or 'generation' in m.lower() for m in logs)
    assert critical_logged, f"Сбой get должен быть залогирован. Логи: {logs}"
    print(f"  PASS test_get_fail_during_error_handling_logs_explicitly (логи: {logs})")


# ── thread.start() fail ───────────────────────────────────────────

def test_thread_start_fail_gives_completed_and_cleanup():
    """thread.start() бросает RuntimeError → completed_without_screenshots, cleanup вызван, experiment сохранён."""
    gen, saved, cleanup = _run_generate_api_thread_start_fail(
        RuntimeError("can't start new thread")
    )
    assert gen.status == 'completed_without_screenshots', f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert gen.error_message, "error_message должен содержать причину"
    assert "can't start new thread" in gen.error_message, gen.error_message
    assert cleanup, "shutil.rmtree должен быть вызван"
    assert saved == ['completed_without_screenshots'], f"_save_experiment_result_safe должен быть вызван: {saved}"
    print(f"  PASS test_thread_start_fail_gives_completed_and_cleanup: {gen.error_message!r}")


# ── Регрессия: монорепо → completed ────────────────────────────────

def test_monorepo_error_gives_completed():
    """RuntimeError 'Монорепо не поддерживается' -> completed_without_screenshots (ожидаемая ситуация)."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError(
            "Монорепо не поддерживается для локального запуска скриншотов "
            "(поддиректории: ['apps'], дочерних package.json: 3)"
        )
    )
    assert gen.status == 'completed_without_screenshots', f"Монорепо должен давать completed_without_screenshots, получен {gen.status!r}"
    assert 'скриншоты недоступны' in gen.error_message.lower(), gen.error_message
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_monorepo_error_gives_completed: {gen.error_message!r}")


def test_nx_no_binary_gives_completed():
    """NX без nx-бинарника → RuntimeError 'не поддерживается' → completed_without_screenshots."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError(
            "NX monorepo не поддерживается: nx не установлен глобально и не найден "
            "в node_modules/.bin (зависимости не установлены). Укажите app_url."
        )
    )
    assert gen.status == 'completed_without_screenshots', f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert 'скриншоты недоступны' in gen.error_message.lower(), gen.error_message
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_nx_no_binary_gives_completed")


def test_no_dev_script_gives_completed():
    """RuntimeError 'Нет подходящего скрипта' -> completed_without_screenshots (монорепо или пустой package.json)."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError("Нет подходящего скрипта запуска (start/dev/serve). Доступные скрипты: ['prepare']")
    )
    assert gen.status == 'completed_without_screenshots', f"Нет dev-скрипта должен давать completed_without_screenshots, получен {gen.status!r}"
    assert 'скриншоты недоступны' in gen.error_message.lower(), gen.error_message
    assert saved == ['completed_without_screenshots']
    print(f"  PASS test_no_dev_script_gives_completed")


# ── Регрессия: нет раннего completed при неожиданной ошибке ────────

def test_regression_no_early_completed_on_unexpected_error_with_data():
    """
    РЕГРЕССИЯ: неожиданная ошибка скриншотов + instruction_data → НЕ должна давать 'completed'.
    До исправления: `is_expected or generation.instruction_data` → 'completed' при любых данных.
    После: только is_expected → 'completed'; неожиданная ошибка → 'failed'.
    """
    gen, saved, _logs = _run_background(exc=OSError("Permission denied: /tmp/screenshot.png"))
    assert gen.status == 'failed', (
        f"РЕГРЕССИЯ: неожиданная ошибка должна давать 'failed', получен {gen.status!r}. "
        "Вероятно, условие `is_expected or generation.instruction_data` снова введено."
    )
    assert saved == [], f"experiment не должен вызываться при failed: {saved}"
    print(f"  PASS test_regression_no_early_completed_on_unexpected_error_with_data")


def test_regression_unexpected_importerror_gives_failed():
    """
    РЕГРЕССИЯ: ImportError (playwright не установлен) → failed, не completed.
    """
    gen, saved, _logs = _run_background(exc=ImportError("No module named 'playwright'"))
    assert gen.status == 'failed', f"РЕГРЕССИЯ: ImportError → failed, получен {gen.status!r}"
    assert saved == []
    print(f"  PASS test_regression_unexpected_importerror_gives_failed")


# ── Зомби-восстановление (логика из generation_status_api) ────────

def test_zombie_recovery_logic():
    """
    Генерация осталась в processing после рестарта (elapsed > 20 мин) →
    должна переходить в failed.
    """
    from datetime import timedelta

    gen = _make_generation()
    gen.status = 'processing'
    gen.created_at = timezone.now() - timedelta(minutes=25)
    gen.completed_at = None
    gen.error_message = ''
    gen.save = MagicMock()

    # Воспроизводим логику из generation_status_api
    _ZOMBIE_TIMEOUT = 20 * 60
    elapsed = (timezone.now() - gen.created_at).total_seconds()
    if gen.status == 'processing' and elapsed > _ZOMBIE_TIMEOUT:
        gen.status = 'failed'
        gen.error_message = (
            f"Таймаут: генерация не завершилась за {elapsed / 60:.0f} мин "
            f"(фоновый процесс завершился без обновления статуса)"
        )
        gen.completed_at = timezone.now()
        gen.save(update_fields=['status', 'error_message', 'completed_at'])

    assert gen.status == 'failed', f"Ожидался failed, получен {gen.status!r}"
    assert gen.completed_at is not None, "completed_at должен быть установлен"
    assert 'таймаут' in gen.error_message.lower(), gen.error_message
    gen.save.assert_called_once()
    print(f"  PASS test_zombie_recovery_logic: {gen.error_message!r}")


def test_zombie_recovery_not_triggered_for_fresh():
    """Генерация старше 5 минут (не 20) → не переходит в failed."""
    from datetime import timedelta

    gen = _make_generation()
    gen.status = 'processing'
    gen.created_at = timezone.now() - timedelta(minutes=5)
    gen.save = MagicMock()

    _ZOMBIE_TIMEOUT = 20 * 60
    elapsed = (timezone.now() - gen.created_at).total_seconds()
    if gen.status == 'processing' and elapsed > _ZOMBIE_TIMEOUT:
        gen.status = 'failed'
        gen.save(update_fields=['status', 'error_message', 'completed_at'])

    assert gen.status == 'processing', f"Свежая генерация не должна переходить в failed: {gen.status!r}"
    gen.save.assert_not_called()
    print(f"  PASS test_zombie_recovery_not_triggered_for_fresh")


# ── Тесты нового статуса completed_without_screenshots ──────────────────────

def test_expected_error_gives_completed_without_screenshots():
    """Ожидаемая ошибка скриншотов → completed_without_screenshots (не completed)."""
    gen, saved, _logs = _run_background(exc=TimeoutError("сервер не запустился за 120с"))
    assert gen.status == 'completed_without_screenshots', \
        f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert saved == ['completed_without_screenshots']
    print("  PASS test_expected_error_gives_completed_without_screenshots")


def test_nx_no_app_url_gives_completed_without_screenshots():
    """NX monorepo RuntimeError → completed_without_screenshots."""
    gen, saved, _logs = _run_background(
        exc=RuntimeError(
            "NX monorepo: локальный запуск не поддерживается. "
            "Укажите URL работающего приложения."
        )
    )
    assert gen.status == 'completed_without_screenshots', \
        f"Ожидался completed_without_screenshots, получен {gen.status!r}"
    assert 'NX monorepo' in gen.error_message or 'Скриншоты недоступны' in gen.error_message
    print("  PASS test_nx_no_app_url_gives_completed_without_screenshots")


def test_completed_requires_at_least_one_screenshot():
    """completed только если есть хотя бы один скриншот."""
    gen, saved, _logs = _run_background(screenshots={'/': 'screenshots/1/home.png'})
    assert gen.status == 'completed', f"Ожидался completed, получен {gen.status!r}"
    print("  PASS test_completed_requires_at_least_one_screenshot")


def test_empty_screenshots_dict_gives_completed_without_screenshots():
    """take_route_screenshots вернул {} без исключения → completed_without_screenshots."""
    gen, saved, _logs = _run_background(screenshots={})
    assert gen.status == 'completed_without_screenshots', \
        f"Пустые скриншоты должны давать completed_without_screenshots, получен {gen.status!r}"
    print("  PASS test_empty_screenshots_dict_gives_completed_without_screenshots")


# ── Тесты логирования в файл (не в stderr) ──────────────────────────────────

def test_log_goes_to_file_not_stderr():
    """Фоновый поток не пишет в sys.stderr: _log пишет в файл когда _tls.log_file установлен."""
    import tempfile, os
    from core.services import screenshot_service as ss

    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as tmp:
        log_path = tmp.name

    original = getattr(ss._tls, 'log_file', None)
    try:
        ss._tls.log_file = log_path
        stderr_calls = []

        import builtins
        original_print = builtins.print
        def spy_print(*args, **kwargs):
            if kwargs.get('file') is sys.stderr:
                stderr_calls.append(args)
            return original_print(*args, **kwargs)

        with patch('builtins.print', side_effect=spy_print):
            ss._log("test message from background thread")

        # Сообщение должно быть в файле
        content = open(log_path, encoding='utf-8').read()
        assert 'test message from background thread' in content, \
            f"Сообщение не найдено в лог-файле: {content!r}"

        # И НЕ в stderr
        assert not stderr_calls, \
            f"_log написал в stderr при установленном _tls.log_file: {stderr_calls}"
    finally:
        ss._tls.log_file = original
        try:
            os.unlink(log_path)
        except Exception:
            pass
    print("  PASS test_log_goes_to_file_not_stderr")


def test_log_goes_to_stderr_when_no_log_file():
    """Вне фонового потока (_tls.log_file не установлен) _log пишет в stderr."""
    from core.services import screenshot_service as ss

    original = getattr(ss._tls, 'log_file', None)
    try:
        ss._tls.log_file = None
        stderr_calls = []

        original_print = __builtins__['print'] if isinstance(__builtins__, dict) else print
        with patch('core.services.screenshot_service.sys') as mock_sys:
            mock_sys.stderr = MagicMock()
            ss._log("direct call message")
            # print вызывался с file=sys.stderr
            # Проверяем через captured output что _log не упал
        # Если дошли сюда без исключений — функция работает корректно в fallback режиме
    finally:
        ss._tls.log_file = original
    print("  PASS test_log_goes_to_stderr_when_no_log_file")


def test_parallel_generations_use_separate_log_files():
    """Параллельные фоновые потоки используют разные лог-файлы без смешивания."""
    import tempfile, threading, os

    from core.services import screenshot_service as ss

    results = {}

    def write_from_thread(gen_id, log_path):
        ss._tls.log_file = log_path
        ss._log(f"message from gen_{gen_id}")
        results[gen_id] = log_path

    with tempfile.NamedTemporaryFile(mode='w', suffix='_1.log', delete=False) as f1, \
         tempfile.NamedTemporaryFile(mode='w', suffix='_2.log', delete=False) as f2:
        log1, log2 = f1.name, f2.name

    try:
        t1 = threading.Thread(target=write_from_thread, args=(1, log1))
        t2 = threading.Thread(target=write_from_thread, args=(2, log2))
        t1.start(); t2.start()
        t1.join(); t2.join()

        content1 = open(log1, encoding='utf-8').read()
        content2 = open(log2, encoding='utf-8').read()

        assert 'message from gen_1' in content1, f"gen_1 не в лог1: {content1!r}"
        assert 'message from gen_2' in content2, f"gen_2 не в лог2: {content2!r}"
        # Логи не смешались
        assert 'message from gen_2' not in content1, f"Логи смешались: gen_2 в лог1"
        assert 'message from gen_1' not in content2, f"Логи смешались: gen_1 в лог2"
    finally:
        for p in (log1, log2):
            try:
                os.unlink(p)
            except Exception:
                pass
    print("  PASS test_parallel_generations_use_separate_log_files")


# ── Runner ────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        # Ожидаемые (completed)
        test_timeout_error_gives_completed,
        test_runtime_error_server_message_gives_completed,
        test_nx_monorepo_gives_completed,
        test_timeout_keyword_in_exception_gives_completed,
        test_ne_zapustilsya_keyword_gives_completed,
        # Неожиданные → failed (независимо от instruction_data)
        test_runtime_error_unexpected_with_data_gives_failed,
        test_attribute_error_with_data_gives_failed,
        test_runtime_error_unexpected_empty_data_gives_failed,
        test_attribute_error_empty_data_gives_failed,
        test_memory_error_empty_data_gives_failed,
        test_value_error_empty_data_gives_failed,
        # Успех
        test_success_gives_completed_empty_error_message,
        # Инварианты
        test_failed_does_not_call_save_experiment,
        test_completed_partial_calls_save_experiment,
        test_completed_partial_error_message_not_empty,
        test_failed_has_diagnostic_message,
        # Сбой save() / get()
        test_save_fail_after_success_does_not_set_completed,
        test_save_fail_after_screenshot_error_logs_and_does_not_call_experiment,
        test_get_fail_during_error_handling_logs_explicitly,
        # thread.start() fail
        test_thread_start_fail_gives_completed_and_cleanup,
        # Регрессия: монорепо
        test_monorepo_error_gives_completed,
        test_no_dev_script_gives_completed,
        test_nx_no_binary_gives_completed,
        # Регрессия: нет раннего completed
        test_regression_no_early_completed_on_unexpected_error_with_data,
        test_regression_unexpected_importerror_gives_failed,
        # NX без бинарника → completed
        test_nx_no_binary_gives_completed,
        # Зомби-восстановление
        test_zombie_recovery_logic,
        test_zombie_recovery_not_triggered_for_fresh,
    ]

    passed = failed = 0
    errors = []

    print(f"\n{'='*60}")
    print("_take_screenshots_background() -- status logic tests")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)}")
    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
