"""
Тесты логики запуска dev-сервера и создания скриншотов.

Сценарии:
1.  Успешная установка и запуск Vite
2.  Ошибка npm install
3.  Несовместимость Node.js (engines warning)
4.  Отсутствующий скрипт запуска
5.  CRA — порт через PORT env var
6.  Next.js — порт уже в скрипте, конфликт не создаётся
7.  Сервер падает сразу после первого HTTP-ответа
8.  Сервер падает во время обхода маршрутов
9.  networkidle не наступает, скриншот всё равно делается
10. Один маршрут падает, остальные продолжаются
11. Файл скриншота не создан — путь не попадает в результат
12. Частично успешная генерация: имеющиеся скриншоты сохраняются
13. Полный отказ скриншотов — RuntimeError с диагностикой
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.screenshot_service import (
    _detect_dev_script,
    _extract_existing_port,
    _get_port_strategy,
    _check_node_engines,
    _npm_install,
    _npm_run_step,
    _uses_hash_router,
    _kill_process_tree,
)


# ── Вспомогательные ──────────────────────────────────────────────────

def _make_project(files: dict) -> str:
    """Создаёт временную директорию с файлами."""
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            full.write_text(json.dumps(content), encoding='utf-8')
        else:
            full.write_text(content, encoding='utf-8')
    return tmp


def _make_pkg(scripts: dict, engines: dict = None) -> dict:
    pkg = {'name': 'test', 'scripts': scripts}
    if engines:
        pkg['engines'] = engines
    return pkg


def _make_server_mock(poll_sequence=None, returncode=None):
    """poll_sequence: список значений poll() по порядку вызовов."""
    server = MagicMock()
    server.returncode = returncode
    if poll_sequence:
        server.poll.side_effect = poll_sequence
    else:
        server.poll.return_value = None  # жив
    server.wait.return_value = 0
    return server


def _make_playwright_mock(page_url='http://127.0.0.1:12345/', screenshot_creates_file=True):
    """Возвращает (mock_sync_playwright, mock_page)."""
    mock_page = MagicMock()
    mock_page.url = page_url
    mock_page.goto.return_value = None
    mock_page.title.return_value = ''
    mock_page.locator.return_value.first.is_visible.return_value = False

    if screenshot_creates_file:
        def fake_screenshot(path, **kwargs):
            Path(path).touch()
        mock_page.screenshot.side_effect = fake_screenshot
    else:
        mock_page.screenshot.return_value = None  # файл не создаётся

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    return mock_sp, mock_page


def _run_take_screenshots(source_path, routes=None, project_id=1,
                           install_rc=0, install_stderr=b'',
                           server_mock=None, playwright_mock=None,
                           wait_for_port_side_effect=None):
    """Запускает take_route_screenshots с замоканными subprocess и playwright."""
    from core.services import screenshot_service

    if routes is None:
        routes = [{'path': '/', 'name': 'Home'}]

    mock_install = MagicMock()
    mock_install.returncode = install_rc
    mock_install.stdout = b''
    mock_install.stderr = install_stderr

    if server_mock is None:
        server_mock = _make_server_mock()

    if playwright_mock is None:
        playwright_mock, _ = _make_playwright_mock()

    # _npm_install теперь использует Popen+wait — мокируем напрямую
    def mock_npm(path):
        if install_rc != 0:
            raise RuntimeError(
                f"npm install завершился с ошибкой.\n"
                f"Стандартный режим (код {install_rc}): "
                + install_stderr.decode('utf-8', errors='ignore')
            )

    with patch('core.services.screenshot_service._npm_install', side_effect=mock_npm), \
         patch.object(screenshot_service.subprocess, 'Popen', return_value=server_mock), \
         patch('core.services.screenshot_service.sync_playwright', playwright_mock), \
         patch('core.services.screenshot_service._wait_for_port',
               side_effect=wait_for_port_side_effect or (lambda *a, **kw: None)), \
         patch('core.services.screenshot_service._find_free_port', return_value=12345), \
         patch('core.services.screenshot_service.time.sleep'):
        result = screenshot_service.take_route_screenshots(source_path, routes, project_id)

    return result


# ── 1. Успешный запуск Vite ─────────────────────────────────────────

def test_vite_success():
    """Vite запускается, скриншот создаётся."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    result = _run_take_screenshots(src)
    assert '/' in result, f"Ожидался скриншот /: {result}"
    assert result['/']['file'].endswith('.png')
    assert result['/']['status'] == 'ok'
    print(f"  PASS test_vite_success: {result}")


# ── 2. Ошибка npm install ────────────────────────────────────────────

def test_npm_install_fails_raises():
    """Оба шага npm install не удались → RuntimeError с диагностикой обоих шагов.

    _run_take_screenshots с install_rc=1 замокает subprocess.run единым mock'ом:
    оба вызова (стандартный и --legacy-peer-deps) вернут returncode=1.
    """
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    try:
        _run_take_screenshots(src, install_rc=1, install_stderr=b'EBADDEVENGINES: node ^24.21.0 required')
        assert False, "Ожидался RuntimeError"
    except RuntimeError as e:
        assert 'npm install завершился с ошибкой' in str(e), str(e)
        assert 'EBADDEVENGINES' in str(e), str(e)
        print(f"  PASS test_npm_install_fails_raises: {e}")


def test_npm_install_standard_success_single_call():
    """Стандартный npm install успешен → _npm_run_step вызывается один раз (без fallback)."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    from core.services import screenshot_service

    with patch('core.services.screenshot_service._npm_run_step', return_value=(0, '')) as mock_step, \
         patch('core.services.screenshot_service._wait_for_port'), \
         patch('core.services.screenshot_service.sync_playwright', _make_playwright_mock()[0]), \
         patch('core.services.screenshot_service._find_free_port', return_value=12345), \
         patch.object(screenshot_service.subprocess, 'Popen', return_value=_make_server_mock()), \
         patch('core.services.screenshot_service.time.sleep'):
        screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 2)

    assert mock_step.call_count == 1, \
        f"Ожидался 1 вызов _npm_run_step, было {mock_step.call_count}"
    call_cmd = mock_step.call_args[0][0]
    assert '--legacy-peer-deps' not in call_cmd, \
        f"Флаг не должен быть в первом вызове: {call_cmd}"
    print(f"  PASS test_npm_install_standard_success_single_call: cmd={call_cmd}")


def test_npm_install_standard_fails_legacy_succeeds():
    """Стандартный install не удался, --legacy-peer-deps успешен → нет ошибки."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    from core.services import screenshot_service

    step_returns = [(1, 'ERESOLVE unable to resolve'), (0, '')]

    with patch('core.services.screenshot_service._npm_run_step', side_effect=step_returns) as mock_step, \
         patch('core.services.screenshot_service.sync_playwright', _make_playwright_mock()[0]), \
         patch('core.services.screenshot_service._wait_for_port'), \
         patch('core.services.screenshot_service._find_free_port', return_value=12345), \
         patch.object(screenshot_service.subprocess, 'Popen', return_value=_make_server_mock()), \
         patch('core.services.screenshot_service.time.sleep'):
        result = screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 3)

    assert '/' in result, f"Скриншот должен быть сделан после fallback: {result}"
    assert mock_step.call_count == 2, \
        f"Ожидалось 2 вызова _npm_run_step, было {mock_step.call_count}"
    print(f"  PASS test_npm_install_standard_fails_legacy_succeeds: {result}")


def test_npm_install_both_fail_raises_with_both_diagnostics():
    """Оба шага npm install не удались → RuntimeError содержит диагностику обоих шагов."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    step_returns = [(1, 'ERESOLVE peer conflict'), (1, 'LEGACY_ERROR forced')]

    with patch('core.services.screenshot_service._npm_run_step', side_effect=step_returns):
        try:
            _npm_install(src)
            assert False, "Ожидался RuntimeError"
        except RuntimeError as e:
            msg = str(e)
            assert 'npm install завершился с ошибкой' in msg, msg
            assert 'ERESOLVE' in msg, f"Диагностика шага 1 отсутствует: {msg}"
            assert 'LEGACY_ERROR' in msg, f"Диагностика шага 2 отсутствует: {msg}"
            print(f"  PASS test_npm_install_both_fail_raises_with_both_diagnostics: OK")


# ── 3. Предупреждение Node.js engines ───────────────────────────────

def test_node_engines_warning_returned():
    """_check_node_engines возвращает строку при несовместимой версии."""
    src = _make_project({'package.json': _make_pkg({'dev': 'next dev'}, engines={'node': '^14 || ^16 || ^18'})})
    with patch('core.services.screenshot_service.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=b'v24.17.0\n', returncode=0)
        warning = _check_node_engines(src)
    assert warning is not None, "Должно быть предупреждение"
    assert 'v24.17.0' in warning, warning
    assert '^14 || ^16 || ^18' in warning, warning
    print(f"  PASS test_node_engines_warning_returned: {warning!r}")


def test_node_engines_no_requirement_returns_none():
    """Если engines.node не указан — None."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    result = _check_node_engines(src)
    assert result is None, f"Ожидался None: {result!r}"
    print(f"  PASS test_node_engines_no_requirement_returns_none")


# ── 4. Отсутствующий скрипт запуска ──────────────────────────────────

def test_no_start_script_raises():
    """Нет start/dev/serve → RuntimeError с перечислением доступных скриптов."""
    src = _make_project({'package.json': _make_pkg({'build': 'tsc', 'lint': 'eslint .'})})
    try:
        _run_take_screenshots(src)
        assert False, "Ожидался RuntimeError"
    except RuntimeError as e:
        assert 'Нет подходящего скрипта запуска' in str(e), str(e)
        assert 'build' in str(e) or 'lint' in str(e), str(e)
        print(f"  PASS test_no_start_script_raises: {e}")


def test_detect_dev_script_returns_none_when_no_script():
    """_detect_dev_script возвращает None если нет подходящего скрипта."""
    src = _make_project({'package.json': _make_pkg({'build': 'tsc'})})
    result = _detect_dev_script(src)
    assert result is None, f"Ожидался None, получен {result!r}"
    print(f"  PASS test_detect_dev_script_returns_none_when_no_script")


# ── 5. CRA — порт через PORT env var ────────────────────────────────

def test_cra_port_strategy_uses_env():
    """react-scripts → _get_port_strategy возвращает PORT в env, не CLI-аргументы."""
    port_args, port_env = _get_port_strategy('react-scripts start', 54321)
    assert port_args == [], f"CRA не должен иметь CLI-аргументов порта: {port_args}"
    assert port_env.get('PORT') == '54321', f"CRA должен использовать PORT env: {port_env}"
    print(f"  PASS test_cra_port_strategy_uses_env: port_args={port_args}, env={port_env}")


def test_cra_screenshots_with_port_env():
    """CRA: команда запускается без --port в CLI, PORT передаётся через env."""
    src = _make_project({'package.json': _make_pkg({'start': 'react-scripts start'})})
    from core.services import screenshot_service
    popen_calls = []

    original_popen = screenshot_service.subprocess.Popen

    def capture_popen(cmd, **kwargs):
        popen_calls.append({'cmd': cmd, 'env': kwargs.get('env', {})})
        return _make_server_mock()

    pw, _ = _make_playwright_mock()

    with patch('core.services.screenshot_service._npm_install'), \
         patch.object(screenshot_service.subprocess, 'Popen', side_effect=capture_popen), \
         patch('core.services.screenshot_service.sync_playwright', pw), \
         patch('core.services.screenshot_service._wait_for_port'), \
         patch('core.services.screenshot_service._find_free_port', return_value=54321), \
         patch('core.services.screenshot_service.time.sleep'):
        try:
            screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 1)
        except Exception:
            pass

    # popen_calls[0] — Vite (npm install теперь замокан напрямую)
    assert popen_calls, "Popen должен быть вызван (Vite сервер)"
    cmd = popen_calls[0]['cmd']
    env = popen_calls[0]['env']
    assert '--port' not in cmd, f"--port не должен быть в команде CRA: {cmd}"
    assert env.get('PORT') == '54321', f"PORT должен быть в env: {env.get('PORT')}"
    print(f"  PASS test_cra_screenshots_with_port_env: cmd={cmd}, PORT={env.get('PORT')}")


# ── 6. Next.js — порт уже в скрипте ──────────────────────────────────

def test_nextjs_extract_existing_port():
    """_extract_existing_port('next dev --port 3001') → 3001."""
    assert _extract_existing_port('next dev --port 3001') == 3001
    assert _extract_existing_port('next dev -p 3001') == 3001
    assert _extract_existing_port('vite') is None
    assert _extract_existing_port('react-scripts start') is None
    print(f"  PASS test_nextjs_extract_existing_port")


def test_nextjs_uses_existing_port_no_conflict():
    """Next.js с --port 3001 в скрипте: используется порт 3001, не добавляется -p."""
    src = _make_project({'package.json': _make_pkg({'dev': 'next dev --port 3001'})})
    from core.services import screenshot_service
    popen_calls = []

    def capture_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return _make_server_mock()

    pw, _ = _make_playwright_mock(page_url='http://127.0.0.1:3001/')

    def fake_wait_for_port(port, **kwargs):
        assert port == 3001, f"Должен ждать порт 3001, ждёт {port}"

    with patch('core.services.screenshot_service._npm_install'), \
         patch.object(screenshot_service.subprocess, 'Popen', side_effect=capture_popen), \
         patch('core.services.screenshot_service.sync_playwright', pw), \
         patch('core.services.screenshot_service._wait_for_port', side_effect=fake_wait_for_port), \
         patch('core.services.screenshot_service.time.sleep'):
        try:
            screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 1)
        except Exception:
            pass

    assert popen_calls, "Popen должен быть вызван"
    cmd = popen_calls[0]
    assert '-p' not in cmd, f"Лишний -p в команде: {cmd}"
    assert '--port' not in cmd[cmd.index('dev'):] if 'dev' in cmd else True, \
        f"Лишний --port в команде: {cmd}"
    print(f"  PASS test_nextjs_uses_existing_port_no_conflict: cmd={cmd}")


# ── 7. Сервер падает сразу после старта ──────────────────────────────

def test_server_crashes_after_startup_raises():
    """Сервер падает после _wait_for_port + time.sleep → RuntimeError."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    # _wait_for_port замокана и не вызывает poll().
    # Первый реальный вызов poll() — проверка после time.sleep → возвращает 1 (упал).
    server = _make_server_mock(poll_sequence=[1], returncode=1)
    try:
        _run_take_screenshots(src, server_mock=server, project_id=91)
        assert False, "Ожидался RuntimeError"
    except RuntimeError as e:
        assert 'завершился сразу после старта' in str(e), str(e)
        print(f"  PASS test_server_crashes_after_startup_raises: {e}")


# ── 8. Сервер падает во время обхода маршрутов ───────────────────────

def test_server_crashes_during_screenshots_raises():
    """Сервер падает во время обхода маршрутов → RuntimeError."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    # Вызовы poll() в реальном коде (после замоки _wait_for_port и time.sleep):
    # 1. Пост-пауза проверка → None (жив)
    # 2. Перед маршрутом 1   → None (жив)
    # 3. Перед маршрутом 2   → 1   (упал)
    server = _make_server_mock(poll_sequence=[None, None, 1], returncode=1)
    routes = [{'path': '/', 'name': 'Home'}, {'path': '/about', 'name': 'About'}]
    try:
        _run_take_screenshots(src, routes=routes, server_mock=server, project_id=92)
        assert False, "Ожидался RuntimeError"
    except RuntimeError as e:
        assert 'во время обхода маршрутов' in str(e), str(e)
        print(f"  PASS test_server_crashes_during_screenshots_raises: {e}")


# ── 9. networkidle не наступает — скриншот делается ──────────────────

def test_networkidle_timeout_still_screenshots():
    """PlaywrightTimeoutError на networkidle — скриншот всё равно делается."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    mock_page = MagicMock()
    mock_page.url = 'http://127.0.0.1:12345/'
    mock_page.goto.side_effect = PlaywrightTimeoutError("Timeout exceeded")
    mock_page.title.return_value = ''
    mock_page.locator.return_value.first.is_visible.return_value = False

    def fake_screenshot(path, **kwargs):
        Path(path).touch()
    mock_page.screenshot.side_effect = fake_screenshot

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser
    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    result = _run_take_screenshots(src, playwright_mock=mock_sp)
    assert '/' in result, f"Скриншот должен быть сделан несмотря на timeout: {result}"
    assert result['/']['file'].endswith('.png'), f"Ожидался файл скриншота: {result['/']}"
    print(f"  PASS test_networkidle_timeout_still_screenshots: {result}")


# ── 10. Один маршрут падает, остальные продолжаются ──────────────────

def test_one_route_fails_others_continue():
    """Exception на одном маршруте не прерывает остальные."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    call_count = [0]
    current_url = ['http://127.0.0.1:12345/']

    mock_page = MagicMock()
    mock_page.title.return_value = ''
    mock_page.locator.return_value.first.is_visible.return_value = False

    def fake_goto(url, **kwargs):
        call_count[0] += 1
        if '/fail' in url:
            raise Exception("ERR_CONNECTION_REFUSED")
        current_url[0] = url.split('?')[0]

    def fake_screenshot(path, **kwargs):
        Path(path).touch()

    mock_page.goto.side_effect = fake_goto
    mock_page.screenshot.side_effect = fake_screenshot
    type(mock_page).url = property(lambda self: current_url[0])

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser
    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    routes = [
        {'path': '/', 'name': 'Home'},
        {'path': '/fail', 'name': 'Fail'},
        {'path': '/about', 'name': 'About'},
    ]
    result = _run_take_screenshots(src, routes=routes, playwright_mock=mock_sp)

    assert '/' in result, f"/ должен быть в результате: {result}"
    assert '/about' in result, f"/about должен быть в результате: {result}"
    assert '/fail' not in result, f"/fail не должен быть в результате: {result}"
    print(f"  PASS test_one_route_fails_others_continue: {result}")


# ── 11. Файл скриншота не создан — путь не попадает в результат ──────

def test_screenshot_path_not_added_if_file_missing():
    """page.screenshot() вызван, но файл не создан → путь не попадает в результат."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    pw, mock_page = _make_playwright_mock(screenshot_creates_file=False)
    # screenshot() вызывается, но ничего не создаёт (side_effect=None уже установлен в helper)

    try:
        # project_id=99 — гарантируем отсутствие файлов от других тестов
        result = _run_take_screenshots(src, playwright_mock=pw, project_id=99)
        # Если 0 скриншотов и сервер жив — RuntimeError
        assert False, f"Ожидался RuntimeError (0 скриншотов), получен: {result}"
    except RuntimeError as e:
        assert 'не открылись' in str(e) or 'скриншоты не созданы' in str(e), str(e)
        print(f"  PASS test_screenshot_path_not_added_if_file_missing: {e}")


# ── 12. Частичные скриншоты сохраняются ──────────────────────────────

def test_partial_screenshots_returned():
    """Маршруты 1 и 3 успешны, маршрут 2 падает — результат содержит 1 и 3."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    current_url = ['http://127.0.0.1:12345/']

    mock_page = MagicMock()
    mock_page.title.return_value = ''
    mock_page.locator.return_value.first.is_visible.return_value = False

    def fake_goto(url, **kwargs):
        if '/fail' in url:
            raise Exception("page crash")
        current_url[0] = url.split('?')[0]

    def fake_screenshot(path, **kwargs):
        Path(path).touch()

    mock_page.goto.side_effect = fake_goto
    mock_page.screenshot.side_effect = fake_screenshot
    type(mock_page).url = property(lambda self: current_url[0])

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser
    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    routes = [
        {'path': '/home', 'name': 'Home'},
        {'path': '/fail', 'name': 'Fail'},
        {'path': '/settings', 'name': 'Settings'},
    ]
    result = _run_take_screenshots(src, routes=routes, playwright_mock=mock_sp)
    assert '/home' in result, f"/home должен быть в результате: {result}"
    assert '/settings' in result, f"/settings должен быть в результате: {result}"
    assert '/fail' not in result, f"/fail не должен быть в результате: {result}"
    print(f"  PASS test_partial_screenshots_returned: {result}")


# ── 13. Полный отказ скриншотов — RuntimeError с диагностикой ────────

def test_all_routes_fail_raises_with_diagnostic():
    """Все маршруты падают, сервер жив → RuntimeError с количеством ошибок."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    mock_page = MagicMock()
    mock_page.url = 'http://127.0.0.1:12345/'
    mock_page.goto.side_effect = Exception("ERR_CONNECTION_REFUSED")

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser
    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    routes = [{'path': '/', 'name': 'Home'}, {'path': '/about', 'name': 'About'}]
    try:
        _run_take_screenshots(src, routes=routes, playwright_mock=mock_sp)
        assert False, "Ожидался RuntimeError"
    except RuntimeError as e:
        assert 'Все маршруты не открылись' in str(e), str(e)
        assert '2 ошибок' in str(e) or 'ERR_CONNECTION_REFUSED' in str(e), str(e)
        print(f"  PASS test_all_routes_fail_raises_with_diagnostic: {e}")


# ── _uses_hash_router: не трогает node_modules ───────────────────────

def test_uses_hash_router_finds_in_src():
    """_uses_hash_router находит HashRouter в src/ директории."""
    src = _make_project({
        'package.json': _make_pkg({'dev': 'vite'}),
        'src/App.tsx': 'import { HashRouter } from "react-router-dom";\nexport default App;',
    })
    assert _uses_hash_router(src) is True
    print(f"  PASS test_uses_hash_router_finds_in_src")


def test_uses_hash_router_returns_false_without_hash():
    """_uses_hash_router возвращает False если HashRouter нигде нет."""
    src = _make_project({
        'package.json': _make_pkg({'dev': 'vite'}),
        'src/App.tsx': 'import { BrowserRouter } from "react-router-dom";\nexport default App;',
    })
    assert _uses_hash_router(src) is False
    print(f"  PASS test_uses_hash_router_returns_false_without_hash")


def test_uses_hash_router_does_not_scan_node_modules():
    """_uses_hash_router НЕ сканирует node_modules — только src/ и аналогичные."""
    src = _make_project({
        'package.json': _make_pkg({'dev': 'vite'}),
        'src/App.tsx': 'import { BrowserRouter } from "react-router-dom";',
        # HashRouter есть только в node_modules — не должен быть найден
        'node_modules/some-lib/index.js': 'module.exports = { HashRouter: function(){} };',
    })
    result = _uses_hash_router(src)
    assert result is False, "node_modules не должен сканироваться"
    print(f"  PASS test_uses_hash_router_does_not_scan_node_modules")


def test_uses_hash_router_checks_app_and_pages():
    """_uses_hash_router проверяет app/ и pages/ директории."""
    src = _make_project({
        'package.json': _make_pkg({'dev': 'next dev'}),
        'app/layout.tsx': '// no hash',
        'pages/index.tsx': 'import { HashRouter } from "react-router-dom";',
    })
    assert _uses_hash_router(src) is True
    print(f"  PASS test_uses_hash_router_checks_app_and_pages")


# ── 14. Popen вызывается с DEVNULL перенаправлением ──────────────────

def test_popen_uses_devnull_redirects():
    """Vite subprocess.Popen должен получить stdout=DEVNULL, stderr=STDOUT, stdin=DEVNULL."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    from core.services import screenshot_service

    vite_popen_kwargs = {}

    def capture_vite_popen(cmd, **kwargs):
        # Захватываем только первый вызов — это Vite-сервер (npm run dev).
        # subprocess.run внутри _kill_process_tree тоже создаёт Popen,
        # поэтому используем update только для первого вызова.
        if not vite_popen_kwargs:
            vite_popen_kwargs.update(kwargs)
        return _make_server_mock()

    pw, _ = _make_playwright_mock()

    # _npm_install замокан напрямую — Popen вызывается только для Vite
    with patch('core.services.screenshot_service._npm_install'), \
         patch.object(screenshot_service.subprocess, 'Popen', side_effect=capture_vite_popen), \
         patch('core.services.screenshot_service.sync_playwright', pw), \
         patch('core.services.screenshot_service._wait_for_port'), \
         patch('core.services.screenshot_service._find_free_port', return_value=12345), \
         patch('core.services.screenshot_service.time.sleep'):
        try:
            screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 4)
        except Exception:
            pass

    assert vite_popen_kwargs.get('stdout') == screenshot_service.subprocess.DEVNULL, \
        f"stdout должен быть DEVNULL: {vite_popen_kwargs.get('stdout')}"
    assert vite_popen_kwargs.get('stderr') == screenshot_service.subprocess.STDOUT, \
        f"stderr должен быть STDOUT: {vite_popen_kwargs.get('stderr')}"
    assert vite_popen_kwargs.get('stdin') == screenshot_service.subprocess.DEVNULL, \
        f"stdin должен быть DEVNULL: {vite_popen_kwargs.get('stdin')}"
    print(f"  PASS test_popen_uses_devnull_redirects: stdout/stderr/stdin корректны")


# ── 15. _wait_for_port: порт открывается после нескольких попыток ─────

def test_wait_for_port_succeeds_after_retries():
    """_wait_for_port находит порт на 3-й попытке, не поднимает исключений."""
    import urllib.request as _urllib_request
    from core.services.screenshot_service import _wait_for_port

    attempt = [0]

    def fake_urlopen(url, timeout=None):
        attempt[0] += 1
        if attempt[0] < 3:
            raise OSError("Connection refused")
        # 3-я попытка успешна

    server = _make_server_mock()  # poll() → None (жив)

    with patch.object(_urllib_request, 'urlopen', side_effect=fake_urlopen), \
         patch('core.services.screenshot_service.time.sleep'):
        _wait_for_port(12345, timeout=60, process=server)

    assert attempt[0] == 3, f"Ожидалось 3 попытки, было {attempt[0]}"
    print(f"  PASS test_wait_for_port_succeeds_after_retries: {attempt[0]} попыток")


# ── 16. _wait_for_port: сервер умер в ожидании ────────────────────────

def test_wait_for_port_raises_if_server_dies():
    """_wait_for_port поднимает RuntimeError если сервер завершился в ожидании."""
    import urllib.request as _urllib_request
    from core.services.screenshot_service import _wait_for_port

    def always_fail(url, timeout=None):
        raise OSError("Connection refused")

    server = _make_server_mock(poll_sequence=[None, 1], returncode=3)

    with patch.object(_urllib_request, 'urlopen', side_effect=always_fail), \
         patch('core.services.screenshot_service.time.sleep'):
        try:
            _wait_for_port(12345, timeout=60, process=server)
            assert False, "Ожидался RuntimeError"
        except RuntimeError as e:
            assert '3' in str(e), f"Код возврата должен быть в сообщении: {e}"
            print(f"  PASS test_wait_for_port_raises_if_server_dies: {e}")


# ── 17. _uses_hash_router вызывается ДО Popen ────────────────────────

def test_uses_hash_router_called_before_popen():
    """_uses_hash_router должна вызываться до subprocess.Popen."""
    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    from core.services import screenshot_service

    call_order = []

    original_hash_router = screenshot_service._uses_hash_router
    original_popen = screenshot_service.subprocess.Popen

    def track_hash_router(path):
        call_order.append('hash_router')
        return False

    def track_popen(cmd, **kwargs):
        call_order.append('popen')
        return _make_server_mock()

    pw, _ = _make_playwright_mock()

    with patch('core.services.screenshot_service._npm_install'), \
         patch.object(screenshot_service.subprocess, 'Popen', side_effect=track_popen), \
         patch('core.services.screenshot_service._uses_hash_router', side_effect=track_hash_router), \
         patch('core.services.screenshot_service.sync_playwright', pw), \
         patch('core.services.screenshot_service._wait_for_port'), \
         patch('core.services.screenshot_service._find_free_port', return_value=12345), \
         patch('core.services.screenshot_service.time.sleep'):
        try:
            screenshot_service.take_route_screenshots(src, [{'path': '/', 'name': 'Home'}], 5)
        except Exception:
            pass

    assert 'hash_router' in call_order, "hash_router не был вызван"
    assert 'popen' in call_order, "popen не был вызван"
    hash_idx = call_order.index('hash_router')
    popen_idx = call_order.index('popen')
    assert hash_idx < popen_idx, \
        f"hash_router ({hash_idx}) должен быть вызван ДО popen ({popen_idx}): {call_order}"
    print(f"  PASS test_uses_hash_router_called_before_popen: порядок {call_order}")


# ── 18. _log пишет в stderr, не в stdout ─────────────────────────────

def test_log_writes_to_stderr_not_stdout():
    """_log должен писать в sys.stderr, а не в sys.stdout — иначе flush блокирует."""
    import io
    from core.services import screenshot_service
    from core.services.screenshot_service import _log, _tls

    fake_stdout = io.StringIO()
    fake_stderr = io.StringIO()

    # Убираем log_file чтобы _log не ушёл в файл
    old_log_file = getattr(_tls, 'log_file', None)
    _tls.log_file = None
    try:
        with patch('sys.stdout', fake_stdout), patch('sys.stderr', fake_stderr):
            _log("тест вывода")
    finally:
        _tls.log_file = old_log_file

    assert fake_stdout.getvalue() == '', \
        f"stdout должен быть пуст: {fake_stdout.getvalue()!r}"
    assert "тест вывода" in fake_stderr.getvalue(), \
        f"stderr должен содержать сообщение: {fake_stderr.getvalue()!r}"
    print(f"  PASS test_log_writes_to_stderr_not_stdout")


# ── 19. _npm_run_step: stdout=file (не PIPE), stdin=DEVNULL ──────────

def test_npm_run_step_no_pipe_stdout():
    """_npm_run_step передаёт stdout=file (не PIPE) Popen — нет блокировки буфера."""
    import subprocess as _subprocess
    from core.services import screenshot_service

    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    captured = {}

    def capture_popen(cmd, **kwargs):
        captured['stdin'] = kwargs.get('stdin')
        captured['stdout'] = kwargs.get('stdout')
        captured['stderr'] = kwargs.get('stderr')
        m = MagicMock()
        m.pid = 42
        m.returncode = 0
        m.wait.return_value = 0
        return m

    with patch.object(screenshot_service.subprocess, 'Popen', side_effect=capture_popen):
        screenshot_service._npm_run_step(
            [screenshot_service.NPM, 'install'], src, timeout_sec=60, label='test'
        )

    assert captured.get('stdin') == _subprocess.DEVNULL, \
        f"stdin должен быть DEVNULL: {captured.get('stdin')!r}"
    assert captured.get('stdout') != _subprocess.PIPE, \
        "stdout не должен быть PIPE — риск блокировки буфера на Windows"
    assert captured.get('stderr') == _subprocess.STDOUT, \
        f"stderr должен быть STDOUT (объединение в файл): {captured.get('stderr')!r}"
    # stdout должен быть файловым объектом (не PIPE, не DEVNULL)
    assert hasattr(captured.get('stdout'), 'write'), \
        f"stdout должен быть файлом: {type(captured.get('stdout'))}"
    print(f"  PASS test_npm_run_step_no_pipe_stdout: stdin/stdout/stderr корректны")


# ── 20. _npm_run_step: таймаут — kill, proc.wait, диагностика, удаление ─

def test_npm_run_step_timeout_kills_process_tree():
    """При таймауте: kill вызван, proc.wait вызван, диагностика в ошибке, файл удалён."""
    import subprocess as _subprocess
    import os
    from core.services import screenshot_service

    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    killed_pids = []
    wait_calls = []  # записываем все вызовы wait с аргументами
    created_log_path = []  # захватим путь к temp-файлу

    def fake_popen(cmd, **kwargs):
        m = MagicMock()
        m.pid = 5555
        m.returncode = None

        # Записываем диагностику в лог-файл, переданный как stdout
        log_f = kwargs.get('stdout')
        if hasattr(log_f, 'write'):
            log_f.write(b'npm warn ERESOLVE forced\nnpm error code ERESOLVE')
            log_f.flush()
            # Захватываем путь до закрытия файла
            if hasattr(log_f, 'name'):
                created_log_path.append(log_f.name)

        def fake_wait(timeout=None):
            wait_calls.append(timeout)
            if len(wait_calls) == 1:
                # Основной вызов — таймаут
                raise _subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
            # Второй вызов после kill — завершается нормально

        m.wait.side_effect = fake_wait
        return m

    with patch.object(screenshot_service.subprocess, 'Popen', side_effect=fake_popen), \
         patch('core.services.screenshot_service._kill_process_tree',
               side_effect=lambda pid: killed_pids.append(pid)):
        try:
            screenshot_service._npm_run_step(
                [screenshot_service.NPM, 'install'], src, timeout_sec=1, label='test'
            )
            assert False, "Ожидался RuntimeError"
        except RuntimeError as e:
            err_msg = str(e)
            # 1. сообщение содержит 'таймаут'
            assert 'таймаут' in err_msg.lower(), \
                f"Сообщение должно содержать 'таймаут': {err_msg}"
            # 2. диагностический вывод из файла включён в ошибку
            assert 'ERESOLVE' in err_msg, \
                f"Диагностика из лог-файла должна быть в ошибке: {err_msg!r}"

    # 3. _kill_process_tree вызван с правильным PID
    assert 5555 in killed_pids, f"Должен убить pid=5555: {killed_pids}"

    # 4. proc.wait вызван дважды: основной таймаут + cleanup(timeout=10)
    assert len(wait_calls) >= 2, f"proc.wait должен быть вызван дважды: {wait_calls}"
    assert wait_calls[1] == 10, \
        f"Второй вызов proc.wait должен иметь timeout=10: {wait_calls}"

    # 5. temp-файл удалён (если путь захвачен)
    if created_log_path:
        assert not os.path.exists(created_log_path[0]), \
            f"Временный лог-файл должен быть удалён: {created_log_path[0]}"

    print(f"  PASS test_npm_run_step_timeout_kills_process_tree: "
          f"killed={killed_pids}, wait_calls={wait_calls}")


# ── 20b. _npm_run_step: ошибка чтения файла не скрывает таймаут ───────

def test_npm_run_step_timeout_file_read_error_not_hidden():
    """Ошибка чтения лог-файла при таймауте не скрывает исходный RuntimeError."""
    import subprocess as _subprocess
    from core.services import screenshot_service

    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})

    def fake_popen(cmd, **kwargs):
        m = MagicMock()
        m.pid = 7777
        m.returncode = None
        m.wait.side_effect = _subprocess.TimeoutExpired(cmd=cmd, timeout=1)
        return m

    # Подменяем Path.read_bytes так, чтобы выбрасывать PermissionError
    import pathlib
    original_read_bytes = pathlib.Path.read_bytes

    def failing_read_bytes(self):
        if '_npm.log' in str(self):
            raise PermissionError("access denied")
        return original_read_bytes(self)

    with patch.object(screenshot_service.subprocess, 'Popen', side_effect=fake_popen), \
         patch('core.services.screenshot_service._kill_process_tree', return_value=None), \
         patch.object(screenshot_service.Path, 'read_bytes', failing_read_bytes):
        try:
            screenshot_service._npm_run_step(
                [screenshot_service.NPM, 'install'], src, timeout_sec=1, label='test'
            )
            assert False, "Ожидался RuntimeError"
        except RuntimeError as e:
            assert 'таймаут' in str(e).lower(), \
                f"RuntimeError о таймауте должен дойти до вызывающего кода: {e}"
        except Exception as e:
            assert False, f"Должен выброситься RuntimeError, не {type(e).__name__}: {e}"

    print(f"  PASS test_npm_run_step_timeout_file_read_error_not_hidden")


# ── 21. _kill_process_tree использует taskkill на Windows ────────────

def test_kill_process_tree_uses_taskkill_on_windows():
    """На Windows _kill_process_tree вызывает taskkill /F /T /PID <pid>."""
    import sys
    if sys.platform != 'win32':
        print("  SKIP test_kill_process_tree_uses_taskkill_on_windows: не Windows")
        return

    from core.services import screenshot_service

    run_calls = []

    def capture_run(cmd, **kwargs):
        run_calls.append(list(cmd))
        return MagicMock(returncode=0)

    with patch.object(screenshot_service.subprocess, 'run', side_effect=capture_run):
        screenshot_service._kill_process_tree(12345)

    assert run_calls, "subprocess.run должен быть вызван"
    cmd = run_calls[0]
    assert any('taskkill' in str(c).lower() for c in cmd), f"taskkill не в команде: {cmd}"
    assert '/F' in cmd, f"/F не в команде: {cmd}"
    assert '/T' in cmd, f"/T не в команде: {cmd}"
    assert str(12345) in [str(c) for c in cmd], f"PID 12345 не в команде: {cmd}"
    print(f"  PASS test_kill_process_tree_uses_taskkill_on_windows: {cmd}")


# ── 22. CREATE_NO_WINDOW в _npm_run_step (Windows) ────────────────────

def test_npm_run_step_uses_create_no_window_on_windows():
    """На Windows _npm_run_step передаёт CREATE_NO_WINDOW в Popen.
    Без этого флага Django (без консоли) создаёт видимое окно cmd.exe,
    уязвимое к случайным CTRL_C_EVENT (STATUS_CONTROL_C_EXIT = 0xC000013A)."""
    import sys
    if sys.platform != 'win32':
        print("  SKIP test_npm_run_step_uses_create_no_window_on_windows: не Windows")
        return

    from core.services import screenshot_service

    src = _make_project({'package.json': _make_pkg({'dev': 'vite'})})
    captured = {}

    def capture_popen(cmd, **kwargs):
        captured['creationflags'] = kwargs.get('creationflags', 0)
        m = MagicMock()
        m.pid = 42
        m.returncode = 0
        m.wait.return_value = 0
        return m

    with patch.object(screenshot_service.subprocess, 'Popen', side_effect=capture_popen):
        screenshot_service._npm_run_step(
            [screenshot_service.NPM, 'install'], src, timeout_sec=60, label='test'
        )

    CREATE_NO_WINDOW = 0x08000000
    flags = captured.get('creationflags', 0)
    assert flags & CREATE_NO_WINDOW, (
        f"CREATE_NO_WINDOW (0x08000000) должен быть в creationflags, получили {flags:#010x}"
    )
    print(f"  PASS test_npm_run_step_uses_create_no_window_on_windows: creationflags={flags:#010x}")


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import shutil
    tests = [
        test_uses_hash_router_finds_in_src,
        test_uses_hash_router_returns_false_without_hash,
        test_uses_hash_router_does_not_scan_node_modules,
        test_uses_hash_router_checks_app_and_pages,
        test_vite_success,
        test_npm_install_fails_raises,
        test_npm_install_standard_success_single_call,
        test_npm_install_standard_fails_legacy_succeeds,
        test_npm_install_both_fail_raises_with_both_diagnostics,
        test_node_engines_warning_returned,
        test_node_engines_no_requirement_returns_none,
        test_no_start_script_raises,
        test_detect_dev_script_returns_none_when_no_script,
        test_cra_port_strategy_uses_env,
        test_cra_screenshots_with_port_env,
        test_nextjs_extract_existing_port,
        test_nextjs_uses_existing_port_no_conflict,
        test_server_crashes_after_startup_raises,
        test_server_crashes_during_screenshots_raises,
        test_networkidle_timeout_still_screenshots,
        test_one_route_fails_others_continue,
        test_screenshot_path_not_added_if_file_missing,
        test_partial_screenshots_returned,
        test_all_routes_fail_raises_with_diagnostic,
        test_popen_uses_devnull_redirects,
        test_wait_for_port_succeeds_after_retries,
        test_wait_for_port_raises_if_server_dies,
        test_uses_hash_router_called_before_popen,
        test_log_writes_to_stderr_not_stdout,
        test_npm_run_step_no_pipe_stdout,
        test_npm_run_step_timeout_kills_process_tree,
        test_npm_run_step_timeout_file_read_error_not_hidden,
        test_kill_process_tree_uses_taskkill_on_windows,
        test_npm_run_step_uses_create_no_window_on_windows,
    ]

    passed = failed = 0

    print(f"\n{'='*60}")
    print("screenshot_service.py — launch & screenshot tests")
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
