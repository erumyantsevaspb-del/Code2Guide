import subprocess
import time
import os
import sys
import shutil
from pathlib import Path
from django.conf import settings

NPM = 'npm.cmd' if sys.platform == 'win32' else 'npm'


def _detect_dev_script(source_path):
    import json
    pkg = Path(source_path) / 'package.json'
    try:
        scripts = json.loads(pkg.read_text(encoding='utf-8')).get('scripts', {})
        # Next.js: next start требует build, используем dev
        start_cmd = scripts.get('start', '')
        if 'next start' in start_cmd and 'dev' in scripts:
            return 'dev'
        for name in ('start', 'dev', 'serve'):
            if name in scripts:
                return name
    except Exception:
        pass
    return 'start'


def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def take_route_screenshots(source_path, routes, project_id):
    """
    Запускает React-приложение и делает скриншоты каждого роута.
    Возвращает словарь {route_path: relative_url_to_screenshot}.
    """
    port = _find_free_port()
    screenshots = {}

    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project_id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    import json as _json
    try:
        pkg_data = _json.loads((Path(source_path) / 'package.json').read_text(encoding='utf-8', errors='ignore'))
        pkg_scripts = pkg_data.get('scripts', {})
    except Exception:
        pkg_scripts = {}

    # Определяем скрипт запуска: start или dev
    dev_script = _detect_dev_script(source_path)
    print(f"Используем скрипт: {dev_script}")

    # Проверяем не является ли проект NX monorepo
    dev_cmd = pkg_scripts.get(dev_script, '')
    if 'nx ' in dev_cmd or 'nx run' in dev_cmd:
        raise RuntimeError("NX monorepo не поддерживается для локального запуска скриншотов")

    is_nextjs = 'next' in dev_cmd

    # Установка зависимостей
    print("Устанавливаем зависимости npm...")
    subprocess.run(
        [NPM, 'install', '--legacy-peer-deps', '--prefer-offline'],
        cwd=source_path,
        capture_output=True,
        timeout=600,
    )

    # Запуск dev-сервера
    print("Запускаем React-приложение...")
    env = os.environ.copy()
    env['BROWSER'] = 'none'
    env['CI'] = 'false'

    if is_nextjs:
        port_args = ['-p', str(port)]
    else:
        port_args = ['--port', str(port), '--host', '0.0.0.0']

    server = subprocess.Popen(
        [NPM, 'run', dev_script, '--'] + port_args,
        cwd=source_path,
        env=env,
    )

    try:
        # Ждём пока сервер запустится
        _wait_for_port(port, timeout=300, process=server)
        print(f"Сервер запущен на порту {port}")
        time.sleep(3)  # доп. пауза для полной загрузки

        # Делаем скриншоты через Playwright
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1280, 'height': 800})

            for route in routes:
                route_path = route.get('path', '/')
                route_name = route.get('name', 'page')

                safe_name = _safe_filename(route_name)
                screenshot_path = screenshots_dir / f"{safe_name}.png"

                if is_nextjs:
                    url = f"http://127.0.0.1:{port}{route_path}"
                else:
                    url = f"http://127.0.0.1:{port}/#/{route_path.lstrip('/')}"

                try:
                    page.goto(url, wait_until='networkidle', timeout=15000)
                    time.sleep(1)
                    final_url = page.url
                    # Пропускаем если редирект на login/auth страницу
                    login_keywords = ('login', 'sign-in', 'signin', 'auth', 'logout')
                    if any(kw in final_url.lower() for kw in login_keywords):
                        print(f"Пропуск (login redirect): {route_name}")
                        continue
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    rel_path = f"screenshots/{project_id}/{safe_name}.png"
                    screenshots[route_path] = rel_path
                    print(f"Скриншот: {route_name} → {safe_name}.png")
                except Exception as e:
                    print(f"Ошибка скриншота {route_name}: {e}")

            browser.close()

    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        print("Сервер остановлен")

    return screenshots


def take_screenshots_with_credentials(app_url, app_login, app_password, routes, project_id):
    """
    Делает скриншоты реального приложения по URL с авторизацией.
    Возвращает {route_path: relative_url_to_screenshot}.
    Пропускает роуты, недоступные для данного пользователя (редирект на login/403).
    """
    from playwright.sync_api import sync_playwright

    screenshots = {}
    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project_id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    base_url = app_url.rstrip('/')
    login_keywords = ('login', 'sign-in', 'signin', 'auth', 'logout', '403', 'forbidden', 'access-denied')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 800})

        # Авторизация
        print(f"Авторизуемся на {base_url}...")
        _do_login(page, base_url, app_login, app_password)

        # Скриншоты каждого роута
        for route in routes:
            route_path = route.get('path', '/')
            route_name = route.get('name', 'page')
            url = f"{base_url}{route_path}"

            safe_name = _safe_filename(route_name)
            screenshot_path = screenshots_dir / f"{safe_name}.png"

            try:
                page.goto(url, wait_until='networkidle', timeout=20000)
                time.sleep(1)
                final_url = page.url

                # Пропускаем если нет доступа
                if any(kw in final_url.lower() for kw in login_keywords):
                    print(f"Нет доступа: {route_name} → {final_url}")
                    continue

                page.screenshot(path=str(screenshot_path), full_page=False)
                rel_path = f"screenshots/{project_id}/{safe_name}.png"
                screenshots[route_path] = rel_path
                print(f"Скриншот: {route_name} → {safe_name}.png")
            except Exception as e:
                print(f"Ошибка скриншота {route_name}: {e}")

        browser.close()

    return screenshots


def _do_login(page, base_url, login, password):
    """Пытается войти в приложение через форму логина."""
    login_urls = [
        f"{base_url}/login",
        f"{base_url}/sign-in",
        f"{base_url}/signin",
        f"{base_url}/auth/login",
        f"{base_url}/auth",
    ]

    for login_url in login_urls:
        try:
            page.goto(login_url, wait_until='networkidle', timeout=10000)
            time.sleep(1)

            # Ищем поле логина/email
            login_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="login"]',
                'input[name="username"]',
                'input[placeholder*="mail" i]',
                'input[placeholder*="логин" i]',
                'input[placeholder*="email" i]',
            ]
            password_selectors = [
                'input[type="password"]',
            ]

            login_field = None
            for sel in login_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        login_field = el
                        break
                except Exception:
                    continue

            password_field = None
            for sel in password_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        password_field = el
                        break
                except Exception:
                    continue

            if not login_field or not password_field:
                continue

            login_field.fill(login)
            password_field.fill(password)

            # Нажимаем кнопку входа
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Войти")',
                'button:has-text("Вход")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
            ]
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        page.wait_for_load_state('networkidle', timeout=10000)
                        print(f"Авторизация выполнена через {login_url}")
                        return
                except Exception:
                    continue

        except Exception as e:
            print(f"Не удалось войти через {login_url}: {e}")
            continue

    print("Авторизация не удалась — продолжаем без неё")


def _wait_for_port(port, timeout=300, process=None):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Dev-сервер завершился с кодом {process.returncode}")
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
            return
        except Exception:
            time.sleep(5)
    raise TimeoutError(f"React-сервер не запустился за {timeout} секунд")


def _safe_filename(name):
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
    return safe.lower()[:50]
