"""
Тесты новых функций screenshot_service.py (V1):

- _extract_existing_port: поддержка --port=3000 (знак равенства)
- _find_runnable_child_app: обнаружение дочернего приложения в монорепо
- login_skipped: RuntimeError когда все маршруты ведут на логин
- bun: RuntimeError когда bun требуется но не установлен
- NX с портом: проход без исключения, NX без порта → исключение
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.screenshot_service import (
    _extract_existing_port,
    _find_runnable_child_app,
)


# ──────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────

def _make_pkg_dir(tmp_root: Path, rel_path: str, scripts: dict, name: str = 'app') -> Path:
    """Создаёт package.json с заданными scripts в нужном поддиректории."""
    d = tmp_root / rel_path
    d.mkdir(parents=True, exist_ok=True)
    (d / 'package.json').write_text(json.dumps({'name': name, 'scripts': scripts}), encoding='utf-8')
    return d


# ──────────────────────────────────────────────────────────────────────
# _extract_existing_port
# ──────────────────────────────────────────────────────────────────────

def test_extract_port_space():
    """--port 3001 (через пробел) → 3001"""
    assert _extract_existing_port('next dev --port 3001') == 3001


def test_extract_port_equals():
    """--port=3000 (через =) → 3000  (NX-стиль)"""
    assert _extract_existing_port('npx nx run crm:serve --configuration=development --port=3000') == 3000


def test_extract_port_short_flag():
    """-p 8080 → 8080"""
    assert _extract_existing_port('vite -p 8080') == 8080


def test_extract_port_none():
    """Нет порта → None"""
    assert _extract_existing_port('vite --host') is None
    assert _extract_existing_port('npm run dev') is None
    assert _extract_existing_port('') is None


# ──────────────────────────────────────────────────────────────────────
# _find_runnable_child_app
# ──────────────────────────────────────────────────────────────────────

def test_find_child_app_vite_in_apps():
    """Единственное Vite-приложение в apps/ → возвращается."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'apps/react-vite', {'dev': 'vite', 'build': 'vite build'}, 'react-vite')
        _make_pkg_dir(root, '', {}, 'root')  # корень без dev-скрипта

        result = _find_runnable_child_app(str(root))
        assert result is not None
        path, script, cmd = result
        assert 'react-vite' in path
        assert script == 'dev'
        assert cmd == 'vite'


def test_find_child_app_prefers_non_nextjs():
    """Если есть Next.js и Vite — выбирается Vite (не-Next.js)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'apps/nextjs-app', {'dev': 'next dev'}, 'nextjs-app')
        _make_pkg_dir(root, 'apps/react-vite', {'dev': 'vite'}, 'react-vite')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is not None
        path, script, cmd = result
        assert 'react-vite' in path
        assert cmd == 'vite'


def test_find_child_app_multiple_nextjs_only():
    """Только Next.js — возвращается первый в алфавитном порядке."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'apps/nextjs-app', {'dev': 'next dev'}, 'nextjs-app')
        _make_pkg_dir(root, 'apps/nextjs-pages', {'dev': 'next dev'}, 'nextjs-pages')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is not None
        # Должен вернуть что-то (логирует предупреждение про несколько)
        assert result[1] == 'dev'


def test_find_child_app_skips_nx():
    """Команда с nx игнорируется."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'apps/crm', {'dev': 'npx nx run crm:serve --port=3000'}, 'crm')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is None


def test_find_child_app_skips_bun():
    """Команда с bun игнорируется."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'apps/saas', {'dev': 'bun run typegen && react-router dev'}, 'saas')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is None


def test_find_child_app_no_monorepo():
    """Нет apps/ или packages/ → None."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'vite'}, 'app')

        result = _find_runnable_child_app(str(root))
        assert result is None


def test_find_child_app_packages_dir():
    """Поддерживается packages/ наряду с apps/."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, 'packages/web', {'dev': 'vite', 'build': 'vite build'}, 'web')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is not None
        path, script, cmd = result
        assert 'web' in path


def test_find_child_app_skips_node_modules():
    """node_modules/some-lib/package.json не считается приложением."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Создаём apps/real с dev-скриптом
        _make_pkg_dir(root, 'apps/real', {'dev': 'vite'}, 'real')
        # Создаём apps/node_modules/fake — должен быть проигнорирован
        _make_pkg_dir(root, 'apps/node_modules/fake', {'dev': 'vite'}, 'fake')
        _make_pkg_dir(root, '', {}, 'root')

        result = _find_runnable_child_app(str(root))
        assert result is not None
        path, _, _ = result
        assert 'real' in path
        assert 'node_modules' not in path


# ──────────────────────────────────────────────────────────────────────
# bun detection (через take_route_screenshots)
# ──────────────────────────────────────────────────────────────────────

def test_bun_not_installed_raises():
    """Если dev-команда требует bun и bun не установлен — RuntimeError с 'не поддерживается'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'bun run typegen && react-router dev'}, 'saas')

        from core.services.screenshot_service import take_route_screenshots
        with patch('shutil.which', return_value=None):  # bun не найден
            try:
                take_route_screenshots(str(root), [{'path': '/', 'name': 'Home'}], project_id=999)
                assert False, "Должен был поднять RuntimeError"
            except RuntimeError as e:
                assert 'не поддерживается' in str(e).lower() or 'bun' in str(e).lower()


def test_bun_installed_no_early_error():
    """Если bun установлен — ранней ошибки bun нет (дальше могут быть другие ошибки)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'bun run dev'}, 'bun-app')

        from core.services.screenshot_service import take_route_screenshots
        # Мокируем всё что идёт после bun-проверки, чтобы не запускать реальный сервер
        with patch('shutil.which', return_value='/usr/bin/bun'), \
             patch('core.services.screenshot_service._npm_install', side_effect=RuntimeError('npm install завершился с ошибкой')):
            try:
                take_route_screenshots(str(root), [{'path': '/', 'name': 'Home'}], project_id=999)
                assert False, "Должен поднять другую ошибку"
            except RuntimeError as e:
                # Должна быть ошибка npm install, а не ошибка bun
                assert 'npm install' in str(e).lower() or 'bun' not in str(e).lower()


# ──────────────────────────────────────────────────────────────────────
# NX port detection
# ──────────────────────────────────────────────────────────────────────

def test_nx_without_port_raises():
    """NX-команда без --port → RuntimeError с 'не поддерживается'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'npx nx run app:serve'}, 'nx-app')

        from core.services.screenshot_service import take_route_screenshots
        try:
            take_route_screenshots(str(root), [{'path': '/', 'name': 'Home'}], project_id=999)
            assert False, "Должен поднять RuntimeError"
        except RuntimeError as e:
            msg = str(e).lower()
            assert 'не поддерживается' in msg or 'порт' in msg


def test_nx_with_port_no_nx_binary_raises():
    """NX-команда с --port=3000, но nx не установлен → ранняя RuntimeError."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'npx nx run crm:serve --port=3000'}, 'nx-app')
        # node_modules/.bin/nx тоже нет (tmp пустой)

        from core.services.screenshot_service import take_route_screenshots
        with patch('shutil.which', return_value=None):  # nx не найден глобально
            try:
                take_route_screenshots(str(root), [{'path': '/', 'name': 'Home'}], project_id=999)
                assert False, "Должен поднять RuntimeError"
            except RuntimeError as e:
                msg = str(e).lower()
                assert 'nx' in msg and ('не поддерживается' in msg or 'не установлен' in msg)


def test_nx_with_port_and_nx_binary_proceeds():
    """NX-команда с --port=3000 и nx доступен → проходит NX-проверку, идёт к npm install."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'npx nx run crm:serve --port=3000'}, 'nx-app')
        # Создаём фиктивный node_modules/.bin/nx чтобы симулировать установленный NX
        nx_bin = Path(tmp) / 'node_modules' / '.bin'
        nx_bin.mkdir(parents=True)
        (nx_bin / 'nx').touch()

        from core.services.screenshot_service import take_route_screenshots
        with patch('core.services.screenshot_service._npm_install',
                   side_effect=RuntimeError('npm install завершился с ошибкой')):
            try:
                take_route_screenshots(str(root), [{'path': '/', 'name': 'Home'}], project_id=999)
                assert False, "Должен поднять ошибку npm install"
            except RuntimeError as e:
                msg = str(e).lower()
                # Должна быть ошибка npm install — NX-проверка прошла
                assert 'npm install' in msg
                assert 'nx monorepo не поддерживается' not in msg


# ──────────────────────────────────────────────────────────────────────
# login_skipped → raise
# ──────────────────────────────────────────────────────────────────────

def test_login_redirect_all_skipped_raises():
    """
    Если все маршруты ведут на логин, take_route_screenshots поднимает RuntimeError
    с ключевыми словами 'все маршруты не открылись' для корректной классификации.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_pkg_dir(root, '', {'dev': 'vite'}, 'vite-app')

        # Мокируем весь стек запуска сервера
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None  # сервер живёт
        fake_proc.pid = 12345

        mock_page = MagicMock()
        mock_page.url = 'http://localhost:3000/login'  # редирект на логин
        mock_page.goto.return_value = None

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_browser.close.return_value = None

        mock_playwright_ctx = MagicMock()
        mock_playwright_ctx.__enter__ = MagicMock(return_value=mock_playwright_ctx)
        mock_playwright_ctx.__exit__ = MagicMock(return_value=False)
        mock_playwright_ctx.chromium.launch.return_value = mock_browser

        from core.services.screenshot_service import take_route_screenshots
        with patch('core.services.screenshot_service._npm_install'), \
             patch('core.services.screenshot_service._uses_hash_router', return_value=False), \
             patch('core.services.screenshot_service._find_free_port', return_value=3000), \
             patch('core.services.screenshot_service._wait_for_port'), \
             patch('core.services.screenshot_service._kill_process_tree'), \
             patch('subprocess.Popen', return_value=fake_proc), \
             patch('core.services.screenshot_service.sync_playwright', return_value=mock_playwright_ctx):
            try:
                take_route_screenshots(
                    str(root),
                    [{'path': '/', 'name': 'Home'}, {'path': '/dashboard', 'name': 'Dashboard'}],
                    project_id=999,
                )
                assert False, "Должен поднять RuntimeError"
            except RuntimeError as e:
                msg = str(e).lower()
                assert 'все маршруты не открылись' in msg, f"Ожидалось 'все маршруты не открылись', получено: {e}"


# ──────────────────────────────────────────────────────────────────────
# _do_login возвращает bool; _page_has_login_form
# ──────────────────────────────────────────────────────────────────────

def test_do_login_returns_false_when_no_form():
    """_do_login возвращает False если форма логина не найдена ни на одном URL."""
    from core.services.screenshot_service import _do_login

    mock_page = MagicMock()
    mock_page.goto.return_value = None
    # is_visible всегда False — форма не найдена
    mock_locator = MagicMock()
    mock_locator.is_visible.return_value = False
    mock_locator.first = mock_locator
    mock_page.locator.return_value = mock_locator

    result = _do_login(mock_page, 'http://localhost:3000', 'user', 'pass')
    assert result is False


def test_do_login_returns_false_when_form_still_present_after_submit():
    """_do_login возвращает False если после нажатия кнопки форма осталась (неверный пароль)."""
    from core.services.screenshot_service import _do_login, _page_has_login_form

    call_count = {'n': 0}

    def make_locator(sel):
        m = MagicMock()
        m.first = m
        if 'password' in sel:
            m.is_visible.return_value = True
        elif sel == 'input[name="username"]':
            m.is_visible.return_value = True
        elif 'submit' in sel or 'Войти' in sel or 'Sign in' in sel or 'Login' in sel or 'Вход' in sel or 'систему' in sel or 'Авторизоваться' in sel:
            m.is_visible.return_value = True
        else:
            m.is_visible.return_value = False
        m.fill.return_value = None
        m.click.return_value = None
        return m

    mock_page = MagicMock()
    mock_page.goto.return_value = None
    mock_page.wait_for_load_state.return_value = None
    mock_page.url = 'http://localhost:3000/login'
    mock_page.locator.side_effect = make_locator

    # После клика форма всё ещё видна (неверные данные)
    with patch('core.services.screenshot_service._page_has_login_form', return_value=True):
        result = _do_login(mock_page, 'http://localhost:3000', 'bad_user', 'bad_pass')

    assert result is False


def test_take_screenshots_with_credentials_raises_when_login_fails():
    """take_screenshots_with_credentials поднимает RuntimeError если авторизация не выполнена."""
    import tempfile
    from core.services.screenshot_service import take_screenshots_with_credentials

    with tempfile.TemporaryDirectory():
        with patch('core.services.screenshot_service._do_login', return_value=False):
            mock_browser = MagicMock()
            mock_page = MagicMock()
            mock_browser.new_page.return_value = mock_page
            mock_browser.close.return_value = None

            mock_pw = MagicMock()
            mock_pw.__enter__ = MagicMock(return_value=mock_pw)
            mock_pw.__exit__ = MagicMock(return_value=False)
            mock_pw.chromium.launch.return_value = mock_browser

            with patch('core.services.screenshot_service.sync_playwright', return_value=mock_pw):
                try:
                    take_screenshots_with_credentials(
                        'http://localhost:3000', 'user', 'pass',
                        [{'path': '/', 'name': 'Home'}],
                        project_id=999,
                    )
                    assert False, "Должен поднять RuntimeError"
                except RuntimeError as e:
                    assert 'авторизация не выполнена' in str(e).lower()


if __name__ == '__main__':
    tests = [
        test_extract_port_space,
        test_extract_port_equals,
        test_extract_port_short_flag,
        test_extract_port_none,
        test_find_child_app_vite_in_apps,
        test_find_child_app_prefers_non_nextjs,
        test_find_child_app_multiple_nextjs_only,
        test_find_child_app_skips_nx,
        test_find_child_app_skips_bun,
        test_find_child_app_no_monorepo,
        test_find_child_app_packages_dir,
        test_find_child_app_skips_node_modules,
        test_bun_not_installed_raises,
        test_bun_installed_no_early_error,
        test_nx_without_port_raises,
        test_nx_with_port_proceeds_past_nx_check,
        test_login_redirect_all_skipped_raises,
        test_do_login_returns_false_when_no_form,
        test_do_login_returns_false_when_form_still_present_after_submit,
        test_take_screenshots_with_credentials_raises_when_login_fails,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f'  OK  {t.__name__}')
            passed += 1
        except Exception as e:
            print(f'FAIL  {t.__name__}: {e}')
            failed += 1
    print(f'\n{passed} passed, {failed} failed')
