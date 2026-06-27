import subprocess
import time
import os
import sys
import shutil
from pathlib import Path
from django.conf import settings

NPM = 'npm.cmd' if sys.platform == 'win32' else 'npm'


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
    env['BROWSER'] = 'none'  # не открывать браузер
    env['CI'] = 'false'

    server = subprocess.Popen(
        [NPM, 'start', '--', '--port', str(port), '--host', '0.0.0.0'],
        cwd=source_path,
        env=env,
    )

    try:
        # Ждём пока сервер запустится
        _wait_for_port(port, timeout=300)
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

                url = f"http://127.0.0.1:{port}/#/{route_path.lstrip('/')}"

                try:
                    page.goto(url, wait_until='networkidle', timeout=15000)
                    time.sleep(1)
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


def _wait_for_port(port, timeout=300):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
            return
        except Exception:
            time.sleep(5)
    raise TimeoutError(f"React-сервер не запустился за {timeout} секунд")


def _safe_filename(name):
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
    return safe.lower()[:50]
