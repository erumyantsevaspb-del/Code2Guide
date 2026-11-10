import subprocess
import tempfile
import time
import os
import sys
import shutil
import threading
from datetime import datetime
from pathlib import Path
from django.conf import settings


def _ts():
    """Метка времени для диагностических логов в формате Django: HH:MM:SS.mmm"""
    return datetime.now().strftime('%H:%M:%S.%f')[:12]


# Thread-local хранилище для пути к лог-файлу.
# Фоновый поток устанавливает _tls.log_file перед вызовом screenshot_service,
# чтобы избежать записи в консоль Windows (Quick Edit Mode блокирует flush).
# Прямые вызовы вне фонового потока не устанавливают _tls.log_file →
# логи по-прежнему идут в stderr.
_tls = threading.local()


def _log(msg):
    line = f"[{_ts()}] {msg}"
    log_path = getattr(_tls, 'log_file', None)
    if log_path:
        try:
            with open(log_path, 'a', encoding='utf-8') as _f:
                _f.write(line + '\n')
            return
        except Exception:
            pass
    # Fallback: stderr для прямых (не фоновых) вызовов
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass


def _kill_process_tree(pid):
    """
    Завершает процесс pid и всё его дерево дочерних процессов.
    На Windows использует taskkill /F /T, на Unix — SIGTERM к группе процессов.
    Молча игнорирует ошибки (процесс мог уже завершиться).
    """
    try:
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    except Exception:
        pass


NPM = 'npm.cmd' if sys.platform == 'win32' else 'npm'
YARN = 'yarn.cmd' if sys.platform == 'win32' else 'yarn'
PNPM = 'pnpm.cmd' if sys.platform == 'win32' else 'pnpm'
NPXCMD = 'npx.cmd' if sys.platform == 'win32' else 'npx'

# Импортируем на уровне модуля для возможности замены в тестах.
# Playwright не является обязательной зависимостью при запуске тестов без браузера.
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightTimeoutError = Exception  # type: ignore[assignment,misc]


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
    return None  # Нет подходящего скрипта — вернём None вместо несуществующего 'start'


def _extract_existing_port(dev_cmd: str):
    """
    Извлекает порт, уже прописанный в команде запуска.
    Пример: 'next dev --port 3001' → 3001, '--port=3000' → 3000, 'vite' → None.
    """
    import re
    m = re.search(r'(?:--port|-p)[=\s]+(\d+)', dev_cmd)
    return int(m.group(1)) if m else None


def _get_port_strategy(dev_cmd: str, port: int):
    """
    Возвращает (port_cli_args, port_env_vars) для конкретного типа dev-сервера.

    CRA (react-scripts): порт только через env PORT; --port игнорируется.
    Next.js: порт через env PORT (CLI порт из скрипта обрабатывается _extract_existing_port).
    Vite: --port через CLI, --host обязателен для 0.0.0.0.
    Generic: пробуем --port.
    """
    if 'react-scripts' in dev_cmd:
        return [], {'PORT': str(port)}
    if 'next' in dev_cmd:
        return [], {'PORT': str(port)}
    if 'vite' in dev_cmd:
        return ['--port', str(port), '--host', '0.0.0.0'], {}
    return ['--port', str(port)], {}


def _check_node_engines(source_path):
    """
    Проверяет совместимость Node.js с полем engines из package.json.
    Возвращает строку-предупреждение или None.
    """
    import json
    pkg = Path(source_path) / 'package.json'
    try:
        engines = json.loads(pkg.read_text(encoding='utf-8', errors='ignore')).get('engines', {})
        req = engines.get('node', '')
        if not req:
            return None
        _CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        installed = result.stdout.decode('utf-8', errors='ignore').strip()
        return f"Node.js {installed} установлен, требуется {req}"
    except Exception:
        return None


def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _npm_run_step(cmd, cwd, timeout_sec, label):
    """
    Запускает npm-команду один раз, направляя stdout+stderr во временный файл.
    Нет PIPE — нет риска блокировки на переполнении буфера (Windows-специфика).
    Возвращает (returncode, last_400_chars_of_output).
    При таймауте убивает дерево процессов через _kill_process_tree.
    """
    t = time.perf_counter()
    fd, log_str = tempfile.mkstemp(suffix='_npm.log')
    os.close(fd)
    log_path = Path(log_str)

    # CREATE_NO_WINDOW: Django работает без консоли (GetConsoleWindow()=0).
    # Без этого флага Windows создаёт видимое окно cmd.exe для npm.cmd,
    # что позволяет случайным CTRL_C_EVENT прерывать npm до завершения установки.
    _CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

    _log(f"{label}: вызываем Popen")
    with open(log_path, 'wb') as log_f:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log_f,
            stderr=subprocess.STDOUT,  # объединяем stdout+stderr → файл
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
    _log(f"{label}: pid={proc.pid}, ждём (таймаут {timeout_sec}с)...")

    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _log(f"{label}: ТАЙМАУТ {timeout_sec}с, убиваем pid={proc.pid}")
        _kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _log(f"{label}: процесс pid={proc.pid} не завершился за 10с после kill")
        diag = ''
        try:
            diag = log_path.read_bytes().decode('utf-8', errors='ignore').strip()[-600:]
        except Exception:
            pass
        try:
            log_path.unlink()
        except Exception:
            pass
        raise RuntimeError(
            f"{label} превысил таймаут {timeout_sec}с\nПоследний вывод npm:\n{diag}"
        )

    rc = proc.returncode
    elapsed = time.perf_counter() - t
    _log(f"{label}: pid={proc.pid} завершился, код={rc}, {elapsed:.1f}с")

    output = ''
    try:
        output = log_path.read_bytes().decode('utf-8', errors='ignore').strip()[-400:]
    except Exception:
        pass
    try:
        log_path.unlink()
    except Exception:
        pass

    return rc, output


def _detect_package_manager(source_path) -> str:
    """
    Определяет пакетный менеджер проекта.
    Возвращает 'yarn', 'pnpm' или 'npm'.

    Приоритет:
      1. Поле packageManager в package.json
      2. Наличие lock-файла: pnpm-lock.yaml → pnpm, yarn.lock → yarn
      3. Иначе → npm
    """
    import json as _json
    source = Path(source_path)
    try:
        pkg = _json.loads((source / 'package.json').read_text(encoding='utf-8', errors='ignore'))
        pm = pkg.get('packageManager', '')
        if pm.startswith('yarn'):
            return 'yarn'
        if pm.startswith('pnpm'):
            return 'pnpm'
        if pm.startswith('npm'):
            return 'npm'
    except Exception:
        pass
    if (source / 'pnpm-lock.yaml').exists():
        return 'pnpm'
    if (source / 'yarn.lock').exists():
        return 'yarn'
    return 'npm'


def _check_private_registry(source_path) -> str | None:
    """
    Сканирует yarn.lock / package-lock.json на упоминание нестандартных registry.
    Возвращает домен первого найденного нестандартного registry или None.

    Функция ИНФОРМАЦИОННАЯ: результат используется только для диагностики.
    Нестандартный registry не означает недоступный — у пользователя может быть
    настроен корректный доступ к нему.

    Игнорируются известные публичные хосты:
      npm-реестры, GitHub, GitLab, CDN и прочие общедоступные сервисы.
    """
    import re
    _KNOWN_PUBLIC = {
        'registry.npmjs.org',
        'registry.yarnpkg.com',
        'npm.pkg.github.com',
        'registry.gitlab.com',
        'codeload.github.com',
        'objects.githubusercontent.com',
        'raw.githubusercontent.com',
        'api.github.com',
        'github.com',
        'gitlab.com',
        'bitbucket.org',
        'unpkg.com',
        'cdn.jsdelivr.net',
    }
    source = Path(source_path)

    for lock_name in ('yarn.lock', 'package-lock.json'):
        lock_path = source / lock_name
        if not lock_path.exists():
            continue
        try:
            content = lock_path.read_bytes()[:200_000].decode('utf-8', errors='ignore')
        except Exception:
            continue

        for m in re.finditer(r'https?://([a-zA-Z0-9._-]+\.[a-zA-Z]{2,})/[^\s\n"]*', content):
            domain = m.group(1).lower()
            if domain not in _KNOWN_PUBLIC:
                _log(f"[REGISTRY] нестандартный registry: {domain}")
                return domain
    return None


def _resolve_yarn_cmd() -> list[str] | None:
    """
    Определяет команду для запуска Yarn.
    Возвращает список аргументов команды или None, если ни Yarn, ни Corepack недоступны.

    Порядок проверки:
      1. yarn / yarn.cmd — прямой Yarn
      2. corepack / corepack.cmd — Corepack (поставляется с Node.js ≥ 16.10)
    """
    COREPACK = 'corepack.cmd' if sys.platform == 'win32' else 'corepack'
    if shutil.which(YARN) or shutil.which('yarn'):
        return [YARN]
    if shutil.which(COREPACK) or shutil.which('corepack'):
        _log("[INSTALL] yarn.cmd не найден, используем corepack yarn")
        return [COREPACK, 'yarn']
    return None


def _install_pnpm(source_path):
    """Устанавливает зависимости для pnpm-проекта."""
    pnpm_bin = shutil.which(PNPM) or shutil.which('pnpm')
    if not pnpm_bin:
        raise RuntimeError(
            "pnpm не поддерживается: менеджер пакетов pnpm не установлен в системе. "
            "Установите pnpm (https://pnpm.io) или укажите app_url в настройках проекта."
        )
    _log("[INSTALL] pnpm install --frozen-lockfile")
    rc, diag = _npm_run_step(
        [PNPM, 'install', '--frozen-lockfile'],
        source_path, timeout_sec=300, label='pnpm install',
    )
    if rc != 0:
        raise RuntimeError(f"pnpm install завершился с ошибкой (код {rc}):\n{diag}")
    _log("[INSTALL] зависимости установлены (pnpm)")


def _install_dependencies(source_path):
    """
    Определяет пакетный менеджер и устанавливает зависимости.

    - pnpm: pnpm install --frozen-lockfile (требует pnpm в PATH)
    - yarn: yarn install --frozen-lockfile
    - npm: двухшаговый install (стандартный + --legacy-peer-deps)

    Нестандартные registry логируются, но установка не блокируется:
    у пользователя может быть настроен корректный доступ.
    При ошибке установки в сообщение добавляется подсказка о registry.
    """
    pm = _detect_package_manager(source_path)
    _log(f"[INSTALL] пакетный менеджер: {pm}")

    # Информационно: нестандартный registry не блокирует установку
    nonstandard_registry = _check_private_registry(source_path)
    if nonstandard_registry:
        _log(f"[INSTALL] нестандартный registry: {nonstandard_registry} (установка продолжается)")

    if pm == 'pnpm':
        _install_pnpm(source_path)
        return

    if pm == 'yarn':
        yarn_cmd = _resolve_yarn_cmd()
        if yarn_cmd is None:
            raise RuntimeError(
                "Yarn не установлен в системе. "
                "Установите Yarn (https://yarnpkg.com) или Corepack (поставляется с Node.js ≥ 16.10), "
                "либо укажите app_url в настройках проекта."
            )
        full_cmd = yarn_cmd + ['install', '--frozen-lockfile']
        label = 'corepack yarn install' if len(yarn_cmd) > 1 else 'yarn install'
        _log(f"[INSTALL] {label}")
        rc, diag = _npm_run_step(full_cmd, source_path, timeout_sec=300, label=label)
        if rc != 0:
            hint = f" (нестандартный registry: {nonstandard_registry})" if nonstandard_registry else ""
            raise RuntimeError(f"{label} завершился с ошибкой (код {rc}){hint}:\n{diag}")
        _log("[INSTALL] зависимости установлены (yarn)")
        return

    # npm
    try:
        _npm_install(source_path)
    except RuntimeError as e:
        if nonstandard_registry:
            raise RuntimeError(
                f"Не удалось установить зависимости (нестандартный registry: {nonstandard_registry}):\n{e}"
            ) from e
        raise


def _npm_install(source_path):
    """
    Устанавливает зависимости npm в два шага.

    Шаг 1: стандартная установка — npm 7+ устанавливает peerDependencies,
            что необходимо для пакетов вроде recharts (peer: react-is).
    Шаг 2: при неудаче — повтор с --legacy-peer-deps для старых проектов
            с реальными конфликтами peerDep (поведение npm 6).

    Каждый шаг: один запуск Popen, вывод во временный файл (без PIPE).
    Raises RuntimeError если оба шага не удались.
    """
    t0 = time.perf_counter()
    _log("npm install: старт (стандартный режим)")

    rc1, diag1 = _npm_run_step(
        [NPM, 'install'], source_path, timeout_sec=300,
        label="npm install",
    )
    _log(f"npm install: итого {time.perf_counter()-t0:.1f}с, код={rc1}")

    if rc1 == 0:
        _log("Зависимости установлены (стандартный режим).")
        return

    _log(f"Стандартная установка не удалась (код {rc1}), пробуем --legacy-peer-deps...")

    t1 = time.perf_counter()
    rc2, diag2 = _npm_run_step(
        [NPM, 'install', '--legacy-peer-deps'], source_path, timeout_sec=300,
        label="npm install --legacy-peer-deps",
    )
    _log(f"npm install --legacy-peer-deps: итого {time.perf_counter()-t1:.1f}с, код={rc2}")

    if rc2 == 0:
        _log("Зависимости установлены (--legacy-peer-deps).")
        return

    raise RuntimeError(
        f"npm install завершился с ошибкой.\n"
        f"Стандартный режим (код {rc1}): {diag1}\n"
        f"--legacy-peer-deps (код {rc2}): {diag2}"
    )


def _find_runnable_child_app(source_path):
    """
    В монорепозитории без dev-скрипта в корне ищет дочернее приложение
    в apps/ или packages/, которое можно запустить напрямую (не NX, не bun).

    Возвращает (child_path_str, script_name, script_cmd) или None.
    Предпочитает non-Next.js приложения (Vite / CRA / React Router).
    """
    import json as _json
    source = Path(source_path)
    candidates = []
    for d in ('apps', 'packages'):
        subdir = source / d
        if not subdir.is_dir():
            continue
        for child_pkg in sorted(subdir.glob('*/package.json')):
            if 'node_modules' in child_pkg.parts:
                continue
            try:
                scripts = _json.loads(child_pkg.read_text(encoding='utf-8', errors='ignore')).get('scripts', {})
            except Exception:
                continue
            for sname in ('dev', 'start', 'serve'):
                if sname not in scripts:
                    continue
                scmd = scripts[sname]
                # Пропускаем команды, требующие NX или bun
                if 'nx ' in scmd or 'nx run' in scmd:
                    break
                if scmd.lstrip().startswith('bun ') or ' bun ' in scmd:
                    break
                candidates.append((str(child_pkg.parent), sname, scmd))
                break

    if not candidates:
        return None

    # Предпочитаем не-Next.js приложения (Vite / CRA), потому что маршруты
    # в монорепо чаще обнаруживаются в SPA-части, а не в Next.js
    non_next = [(p, s, c) for p, s, c in candidates if 'next' not in c.lower()]
    shortlist = non_next if non_next else candidates

    if len(shortlist) == 1:
        return shortlist[0]
    # Если несколько — берём первый (алфавитный порядок, apps/ перед packages/)
    # и логируем предупреждение; вернём первый вариант
    _log(f"Монорепо: несколько дочерних приложений {[Path(p).name for p,_,_ in shortlist]}, "
         f"используем первое: {Path(shortlist[0][0]).name}")
    return shortlist[0]


def find_nx_serve_apps(source_path):
    """
    Ищет NX-приложения с target 'serve' в apps/*/project.json.
    Возвращает список имён NX-проектов (поле 'name' из project.json).
    """
    import json as _json
    source = Path(source_path)
    apps_dir = source / 'apps'
    result = []
    if not apps_dir.is_dir():
        return result
    for pj in sorted(apps_dir.glob('*/project.json')):
        if 'node_modules' in pj.parts:
            continue
        try:
            data = _json.loads(pj.read_text(encoding='utf-8', errors='ignore'))
        except Exception:
            continue
        name = data.get('name', '')
        targets = data.get('targets', {})
        if name and 'serve' in targets:
            result.append(name)
    return result


def take_nx_screenshots(source_path, nx_app_name, routes, project_id, generation_id=None):
    """
    Устанавливает зависимости, запускает 'npx nx serve <nx_app_name>' на свободном порту
    и делает скриншоты маршрутов через Playwright.

    Аргументы:
        nx_app_name: имя NX-проекта (например 'shell')
    Возвращает словарь {route_path: relative_url_to_screenshot}.
    """
    _log(f"[NX] take_nx_screenshots: app={nx_app_name}, project_id={project_id}")

    _gen_dir = str(generation_id) if generation_id else '_legacy'
    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project_id) / _gen_dir
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    _install_dependencies(source_path)

    port = _find_free_port()
    _log(f"[NX] свободный порт: {port}")

    use_hash = _uses_hash_router(source_path)

    cmd = [NPXCMD, 'nx', 'serve', nx_app_name, '--port', str(port)]
    _CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

    _log(f"[NX] запускаем: {' '.join(cmd)}")
    env = os.environ.copy()
    env['BROWSER'] = 'none'
    env['CI'] = 'false'
    server = subprocess.Popen(
        cmd, cwd=source_path, env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
    )

    screenshots = {}
    try:
        _wait_for_port(port, timeout=300, process=server)
        _log(f"[NX] сервер на порту {port}")
        time.sleep(2)

        if server.poll() is not None:
            raise RuntimeError(f"[NX] dev-сервер завершился сразу (код {server.returncode})")

        route_errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(timeout=30_000)
            page = browser.new_page(viewport={'width': 1280, 'height': 800})

            for route in routes:
                if server.poll() is not None:
                    raise RuntimeError(f"[NX] сервер завершился с кодом {server.returncode}")

                route_path = route.get('path', '/')
                route_name = route.get('name', 'page')
                safe_name = _safe_filename(route_name)
                screenshot_path = screenshots_dir / f"{safe_name}.png"

                if use_hash:
                    url = f"http://127.0.0.1:{port}/#/{route_path.lstrip('/')}"
                else:
                    url = f"http://127.0.0.1:{port}{route_path}"

                if _has_dynamic_segments(route_path):
                    screenshots[route_path] = {
                        'file': None, 'status': 'unavailable',
                        'reason': f"Динамический маршрут: {route_path}",
                        'final_url': '', 'title': '', 'h1': '',
                    }
                    continue

                try:
                    try:
                        page.goto(url, wait_until='networkidle', timeout=10000)
                    except PlaywrightTimeoutError:
                        pass

                    time.sleep(1)
                    final_url = page.url
                    if _is_login_redirect(url, final_url):
                        _log(f"[NX] пропуск (login redirect): {route_name}")
                        continue

                    meta = _page_meta(page)
                    status, reason = _classify_screenshot(route_path, route_name, url, final_url, meta)

                    if status == 'unavailable':
                        screenshots[route_path] = {
                            'file': None, 'status': 'unavailable', 'reason': reason,
                            'final_url': final_url, 'title': meta['title'], 'h1': meta['h1'],
                        }
                        _log(f"[NX] скриншот не сохранён ({reason}): {route_name}")
                        continue

                    page.screenshot(path=str(screenshot_path), full_page=False, timeout=15_000)
                    if screenshot_path.exists():
                        rel_path = f"screenshots/{project_id}/{_gen_dir}/{safe_name}.png"
                        screenshots[route_path] = {
                            'file': rel_path, 'status': status, 'reason': reason,
                            'final_url': final_url, 'title': meta['title'], 'h1': meta['h1'],
                        }
                        _log(f"[NX] скриншот: {route_name} статус={status}")
                    else:
                        route_errors.append((route_path, "файл не создан"))
                except Exception as e:
                    route_errors.append((route_path, str(e)))
                    _log(f"[NX] ошибка {route_name}: {e}")

            browser.close()

        real_screenshots = {p: v for p, v in screenshots.items() if v.get('file')}
        if not real_screenshots and route_errors:
            raise RuntimeError(
                f"[NX] все маршруты не открылись: {route_errors[:3]}"
            )
        return screenshots
    finally:
        _kill_process_tree(server.pid)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


_404_TEXTS = (
    'страница не найдена', 'not found', '404', 'page not found',
    'this page could not be found', 'ничего не нашли',
)

# Динамические сегменты: React Router (:id) и Next.js ([id], [...slug])
_DYNAMIC_SEGMENT = __import__('re').compile(r':[a-zA-Z_][a-zA-Z0-9_]*|\[[^\]]+\]')


def _has_dynamic_segments(path: str) -> bool:
    """Возвращает True, если маршрут содержит незаполненные параметры (:id, :userId и т.п.)."""
    return bool(_DYNAMIC_SEGMENT.search(path))


def _page_meta(page) -> dict:
    """
    Считывает из Playwright-страницы:
      - title: document.title
      - h1: текст первого видимого h1 (или пустая строка)
    Не бросает исключений.
    """
    meta = {'title': '', 'h1': ''}
    try:
        meta['title'] = page.title() or ''
    except Exception:
        pass
    try:
        h1 = page.locator('h1').first
        if h1.is_visible(timeout=500):
            meta['h1'] = (h1.inner_text() or '').strip()[:200]
    except Exception:
        pass
    return meta


def _classify_screenshot(
    route_path: str,
    route_name: str,
    requested_url: str,
    final_url: str,
    meta: dict,
) -> tuple[str, str]:
    """
    Определяет статус скриншота.

    Возвращает (status, reason):
      - ('ok', '')              — скриншот корректен
      - ('unavailable', ...)    — скриншот не нужно прикреплять
      - ('needs_review', ...)   — URL совпадает, но заголовок подозрителен
    """
    import re as _re

    # 1. Динамический маршрут без конкретного значения
    if _has_dynamic_segments(route_path):
        return ('unavailable', f"Динамический маршрут: {route_path}")

    # 2. Извлекаем путь из финального URL (без протокола/хоста/хэша)
    final_path = final_url
    try:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(final_url)
        # Для HashRouter путь живёт во фрагменте
        fragment = parsed.fragment.lstrip('/')
        if fragment:
            final_path = '/' + fragment.split('?')[0]
        else:
            final_path = parsed.path or '/'
        final_path = unquote(final_path).rstrip('/') or '/'
    except Exception:
        pass

    norm_requested = route_path.rstrip('/') or '/'

    # 3. Финальный путь отличается от запрошенного (редирект)
    if final_path != norm_requested:
        return ('unavailable', f"Редирект: {route_path} → {final_path}")

    # 4. Признаки 404 в заголовке или h1
    page_text = (meta.get('title', '') + ' ' + meta.get('h1', '')).lower()
    for marker in _404_TEXTS:
        if marker in page_text:
            return ('unavailable', f"Страница не найдена (404): заголовок «{meta.get('h1') or meta.get('title')}»")

    # 5. Проверка соответствия заголовка названию раздела (needs_review)
    # Сравниваем только если есть и route_name, и h1
    h1 = meta.get('h1', '').lower()
    if h1 and route_name:
        # Нормализуем: оставляем только буквы/цифры для сравнения
        def _tokens(s):
            return set(_re.findall(r'[a-zа-яё0-9]+', s.lower()))
        name_tokens = _tokens(route_name)
        h1_tokens = _tokens(h1)
        # Если нет ни одного общего токена (≥3 символов) — помечаем needs_review
        common = {t for t in name_tokens & h1_tokens if len(t) >= 3}
        if name_tokens and h1_tokens and not common:
            return (
                'needs_review',
                f"Заголовок страницы «{meta.get('h1')}» не совпадает с разделом «{route_name}»",
            )

    return ('ok', '')


def take_route_screenshots(source_path, routes, project_id, generation_id=None):
    """
    Запускает React-приложение и делает скриншоты каждого роута.
    Возвращает словарь {route_path: dict} с ключами:
      file, status, reason, final_url, title, h1.
    Поднимает RuntimeError с диагностикой при полном отказе скриншотов.
    """
    _log(f"[DIAG] take_route_screenshots started, project_id={project_id}")
    _t_trs = time.perf_counter()

    _gen_dir = str(generation_id) if generation_id else '_legacy'
    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project_id) / _gen_dir
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    import json as _json
    try:
        pkg_data = _json.loads((Path(source_path) / 'package.json').read_text(encoding='utf-8', errors='ignore'))
        pkg_scripts = pkg_data.get('scripts', {})
    except Exception:
        pkg_scripts = {}

    # Проверяем совместимость Node.js (диагностика, не блокировка)
    _log(f"[DIAG] _check_node_engines: старт (+{time.perf_counter()-_t_trs:.3f}с)")
    _t_engines = time.perf_counter()
    engines_warning = _check_node_engines(source_path)
    _log(f"[DIAG] _check_node_engines: завершён за {time.perf_counter()-_t_engines:.3f}с")
    if engines_warning:
        _log(f"Предупреждение: {engines_warning}")

    # Определяем скрипт запуска
    _t_detect = time.perf_counter()
    dev_script = _detect_dev_script(source_path)
    _log(f"[DIAG] _detect_dev_script: завершён за {time.perf_counter()-_t_detect:.3f}с, скрипт={dev_script!r}")
    if dev_script is None:
        # Нет dev-скрипта в корне — ищем запускаемое дочернее приложение в apps/ / packages/
        child = _find_runnable_child_app(source_path)
        if child:
            child_path, child_script, child_cmd = child
            _log(f"Монорепо: используем {Path(child_path).name}/{child_script}: {child_cmd[:60]}")
            # Перенаправляем выполнение на дочернее приложение
            source_path = child_path
            try:
                import json as _cjson
                pkg_scripts = _cjson.loads(
                    (Path(source_path) / 'package.json').read_text(encoding='utf-8', errors='ignore')
                ).get('scripts', {})
            except Exception:
                pkg_scripts = {}
            dev_script = child_script
            dev_cmd = child_cmd
        else:
            source = Path(source_path)
            monorepo_dirs = [d for d in ('apps', 'packages') if (source / d).is_dir()]
            if monorepo_dirs:
                raise RuntimeError(
                    f"Монорепо не поддерживается для локального запуска скриншотов "
                    f"(поддиректории: {monorepo_dirs}). "
                    f"Укажите app_url в настройках проекта."
                )
            available = list(pkg_scripts.keys())
            raise RuntimeError(
                f"Нет подходящего скрипта запуска (start/dev/serve). Доступные скрипты: {available}"
            )
    _log(f"Используем скрипт: {dev_script}")

    dev_cmd = pkg_scripts.get(dev_script, '')

    # Bun: если команда требует bun, а он не установлен — ранняя диагностика
    _bun_required = dev_cmd.lstrip().startswith('bun ') or ' bun ' in dev_cmd or '&&' in dev_cmd and 'bun ' in dev_cmd
    if _bun_required and not shutil.which('bun'):
        raise RuntimeError(
            f"Менеджер пакетов bun не поддерживается (не установлен в системе). "
            f"Команда запуска: {dev_cmd[:80]}. "
            f"Установите bun (https://bun.sh) или укажите app_url в настройках проекта."
        )

    # NX: если в команде есть nx, пробуем запустить — но только если порт определён
    is_nx = 'nx ' in dev_cmd or 'nx run' in dev_cmd
    _t_nx = time.perf_counter()
    if is_nx:
        nx_port = _extract_existing_port(dev_cmd)
        if nx_port is None:
            _log(f"[DIAG] NX: нет явного порта в команде '{dev_cmd[:60]}'")
            raise RuntimeError(
                f"NX monorepo не поддерживается: не удалось определить порт из команды '{dev_cmd[:80]}'. "
                f"Укажите app_url в настройках проекта."
            )
        # NX требует глобального или локального nx-бинарника.
        # Без него npm install + запуск сервера займут несколько минут и всё равно завершатся ошибкой.
        _nx_local = (
            Path(source_path) / 'node_modules' / '.bin' / 'nx'
        ).exists() or (
            Path(source_path) / 'node_modules' / '.bin' / 'nx.cmd'
        ).exists()
        _nx_available = shutil.which('nx') is not None or _nx_local
        if not _nx_available:
            _log(f"[DIAG] NX: nx-бинарник не найден (глобально и в node_modules/.bin)")
            raise RuntimeError(
                f"NX monorepo не поддерживается: nx не установлен глобально и не найден "
                f"в node_modules/.bin (зависимости не установлены). "
                f"Укажите app_url в настройках проекта."
            )
        _log(f"[DIAG] NX: порт {nx_port} из команды, nx доступен, запускаем через npm run {dev_script}")
    _log(f"[DIAG] NX-проверка: {'NX с портом' if is_nx else 'не NX'}, {time.perf_counter()-_t_nx:.3f}с")

    is_nextjs = 'next' in dev_cmd
    # NX-проекты требуют больше времени на первую компиляцию
    server_wait_timeout = 240 if is_nx else 120

    # Установка зависимостей
    _log("Устанавливаем зависимости...")
    _install_dependencies(source_path)
    t_after_install = time.perf_counter()
    _log(f"Зависимости установлены. (+{time.perf_counter()-t_after_install:.3f}с до _log)")

    # Определяем тип маршрутизатора ДО запуска сервера.
    # _uses_hash_router сканирует только src/, app/, pages/ — не node_modules.
    t_hash = time.perf_counter()
    use_hash = (not is_nextjs) and _uses_hash_router(source_path)
    _log(f"Тип маршрутизатора: {'HashRouter' if use_hash else 'BrowserRouter/History'} "
         f"(сканирование {time.perf_counter()-t_hash:.2f}с)")

    # Определяем порт
    existing_port = _extract_existing_port(dev_cmd)
    if existing_port:
        port = existing_port
        port_args = []
        port_env = {}
        _log(f"Используем порт из скрипта: {port}")
    else:
        port = _find_free_port()
        port_args, port_env = _get_port_strategy(dev_cmd, port)
        _log(f"Используем свободный порт: {port}")

    cmd = [NPM, 'run', dev_script]
    if port_args:
        cmd += ['--'] + port_args

    # stdout/stderr/stdin перенаправляем в DEVNULL: без этого дочерний процесс
    # может заблокироваться на write() когда буфер консоли Django переполняется.
    # CREATE_NO_WINDOW: та же причина что в _npm_run_step — без консоли у Django
    # Windows создаёт видимое окно для dev-сервера, уязвимое к CTRL_C_EVENT.
    _CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
    _log(f"Запускаем React-приложение: {' '.join(cmd)}")
    env = os.environ.copy()
    env['BROWSER'] = 'none'
    env['CI'] = 'false'
    env.update(port_env)
    server = subprocess.Popen(
        cmd, cwd=source_path, env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
    )

    screenshots = {}
    try:
        # Ждём пока сервер запустится
        t_wait = time.perf_counter()
        _wait_for_port(port, timeout=server_wait_timeout, process=server)
        _log(f"Сервер запущен на порту {port} (ожидание {time.perf_counter()-t_wait:.1f}с)")
        time.sleep(2)  # доп. пауза для полной загрузки

        # Проверяем что процесс ещё жив после паузы
        if server.poll() is not None:
            raise RuntimeError(
                f"Dev-сервер завершился сразу после старта (код {server.returncode})"
            )

        # Делаем скриншоты через Playwright
        route_errors = []
        login_skipped = []

        with sync_playwright() as p:
            browser = p.chromium.launch(timeout=30_000)
            page = browser.new_page(viewport={'width': 1280, 'height': 800})

            for route in routes:
                # Проверяем что сервер ещё жив перед каждым маршрутом
                if server.poll() is not None:
                    raise RuntimeError(
                        f"Dev-сервер завершился с кодом {server.returncode} во время обхода маршрутов"
                    )

                route_path = route.get('path', '/')
                route_name = route.get('name', 'page')

                safe_name = _safe_filename(route_name)
                screenshot_path = screenshots_dir / f"{safe_name}.png"

                if is_nextjs:
                    url = f"http://127.0.0.1:{port}{route_path}"
                elif use_hash:
                    url = f"http://127.0.0.1:{port}/#/{route_path.lstrip('/')}"
                else:
                    url = f"http://127.0.0.1:{port}{route_path}"

                # Ранняя проверка: динамические сегменты без значений
                if _has_dynamic_segments(route_path):
                    screenshots[route_path] = {
                        'file': None,
                        'status': 'unavailable',
                        'reason': f"Динамический маршрут: {route_path}",
                        'final_url': '', 'title': '', 'h1': '',
                    }
                    _log(f"Пропуск (динамический маршрут): {route_name}")
                    continue

                t_route = time.perf_counter()
                try:
                    try:
                        page.goto(url, wait_until='networkidle', timeout=10000)
                    except PlaywrightTimeoutError:
                        # networkidle не наступил — SPA с долгим polling или фоновыми запросами.
                        # Страница уже отрисована, делаем скриншот как есть.
                        pass

                    time.sleep(1)
                    final_url = page.url

                    # Пропускаем если редирект на login/auth страницу
                    if _is_login_redirect(url, final_url):
                        _log(f"Пропуск (login redirect): {route_name} → {final_url}")
                        login_skipped.append(route_path)
                        continue

                    meta = _page_meta(page)
                    status, reason = _classify_screenshot(
                        route_path, route_name, url, final_url, meta
                    )

                    if status == 'unavailable':
                        screenshots[route_path] = {
                            'file': None,
                            'status': 'unavailable',
                            'reason': reason,
                            'final_url': final_url,
                            'title': meta['title'],
                            'h1': meta['h1'],
                        }
                        _log(f"Скриншот не сохранён ({reason}): {route_name}")
                        continue

                    page.screenshot(path=str(screenshot_path), full_page=False, timeout=15_000)

                    # Путь добавляем только если файл реально создан
                    if screenshot_path.exists():
                        rel_path = f"screenshots/{project_id}/{_gen_dir}/{safe_name}.png"
                        screenshots[route_path] = {
                            'file': rel_path,
                            'status': status,
                            'reason': reason,
                            'final_url': final_url,
                            'title': meta['title'],
                            'h1': meta['h1'],
                        }
                        _log(f"Скриншот: {route_name} статус={status} ({time.perf_counter()-t_route:.1f}с)")
                    else:
                        err_msg = f"Файл скриншота не создан: {screenshot_path}"
                        route_errors.append((route_path, err_msg))
                        _log(err_msg)

                except Exception as e:
                    route_errors.append((route_path, str(e)))
                    _log(f"Ошибка скриншота {route_name}: {e}")

            browser.close()

        # Если ни одного скриншота с файлом — поднимаем с диагностикой
        real_screenshots = {p: v for p, v in screenshots.items() if v.get('file')}
        if not real_screenshots:
            if server.poll() is not None:
                raise RuntimeError(
                    f"Dev-сервер завершился с кодом {server.returncode} — скриншоты не созданы"
                )
            if route_errors:
                first_err = route_errors[0][1][:300]
                raise RuntimeError(
                    f"Все маршруты не открылись ({len(route_errors)} ошибок): {first_err}"
                )
            if login_skipped:
                raise RuntimeError(
                    f"Все маршруты не открылись: {len(login_skipped)} из {len(routes)} "
                    f"перенаправлены на страницу авторизации. "
                    f"Укажите app_url + логин/пароль в настройках проекта для создания скриншотов."
                )

    finally:
        t_stop = time.perf_counter()
        # _kill_process_tree убивает cmd.exe + node.exe Vite + все потомки на Windows.
        # server.terminate() убивает только прямой дочерний процесс (cmd.exe),
        # поэтому Vite-процессы накапливались как zombie на предыдущих генерациях.
        _kill_process_tree(server.pid)
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        _log(f"Сервер остановлен (завершение {time.perf_counter()-t_stop:.1f}с)")

    _log(f"take_route_screenshots завершён: {len(screenshots)} скриншотов")
    return screenshots


def take_screenshots_with_credentials(app_url, app_login, app_password, routes, project_id, generation_id=None):
    """
    Делает скриншоты реального приложения по URL с авторизацией.
    Возвращает {route_path: {file, status, reason, final_url, title, h1}}.
    Пропускает роуты, недоступные для данного пользователя (редирект на login/403).
    """
    screenshots = {}
    _gen_dir = str(generation_id) if generation_id else '_legacy'
    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project_id) / _gen_dir
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    base_url = app_url.rstrip('/')
    auth_skipped = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 800})

        # Авторизация — только если заданы оба поля
        if app_login and app_password:
            _log(f"Авторизуемся на {base_url}...")
            login_ok = _do_login(page, base_url, app_login, app_password)
            if not login_ok:
                browser.close()
                raise RuntimeError(
                    f"Авторизация не выполнена: не удалось найти или заполнить форму входа на {base_url}. "
                    f"Проверьте app_url, логин и пароль в настройках проекта."
                )
        else:
            _log(f"Внешний URL без авторизации: {base_url}")

        # Скриншоты каждого роута
        for route in routes:
            route_path = route.get('path', '/')
            route_name = route.get('name', 'page')
            url = f"{base_url}{route_path}"

            safe_name = _safe_filename(route_name)
            screenshot_path = screenshots_dir / f"{safe_name}.png"

            try:
                # Динамические маршруты — пропускаем до запроса
                if _has_dynamic_segments(route_path):
                    screenshots[route_path] = {
                        'file': None,
                        'status': 'unavailable',
                        'reason': f"Динамический маршрут: {route_path}",
                        'final_url': '', 'title': '', 'h1': '',
                    }
                    _log(f"Пропуск (динамический маршрут): {route_name}")
                    continue

                try:
                    page.goto(url, wait_until='networkidle', timeout=20000)
                except PlaywrightTimeoutError:
                    # networkidle не наступил — SPA с polling или фоновыми запросами.
                    # Страница уже отрисована, делаем скриншот как есть.
                    pass

                time.sleep(1)
                final_url = page.url

                # Проверяем URL-редирект на страницу входа
                if _is_login_redirect(url, final_url):
                    _log(f"Нет доступа (URL): {route_name} → {final_url}")
                    auth_skipped.append(route_path)
                    continue

                # Проверяем наличие login-формы на странице (inline auth, без редиректа URL)
                if _page_has_login_form(page):
                    _log(f"Нет доступа (inline login): {route_name}")
                    auth_skipped.append(route_path)
                    continue

                meta = _page_meta(page)
                status, reason = _classify_screenshot(
                    route_path, route_name, url, final_url, meta
                )

                if status == 'unavailable':
                    screenshots[route_path] = {
                        'file': None,
                        'status': 'unavailable',
                        'reason': reason,
                        'final_url': final_url,
                        'title': meta['title'],
                        'h1': meta['h1'],
                    }
                    _log(f"Скриншот не сохранён ({reason}): {route_name}")
                    continue

                page.screenshot(path=str(screenshot_path), full_page=False, timeout=15_000)
                if screenshot_path.exists():
                    rel_path = f"screenshots/{project_id}/{_gen_dir}/{safe_name}.png"
                    screenshots[route_path] = {
                        'file': rel_path,
                        'status': status,
                        'reason': reason,
                        'final_url': final_url,
                        'title': meta['title'],
                        'h1': meta['h1'],
                    }
                    _log(f"Скриншот: {route_name} статус={status} → {safe_name}.png")
                else:
                    _log(f"Файл скриншота не создан: {screenshot_path}")
            except Exception as e:
                _log(f"Ошибка скриншота {route_name}: {e}")

        browser.close()

    real_screenshots = {p: v for p, v in screenshots.items() if v.get('file')}

    if auth_skipped and not real_screenshots:
        raise RuntimeError(
            f"Все маршруты не открылись: {len(auth_skipped)} из {len(routes)} "
            f"недоступны после авторизации. "
            f"Проверьте учётные данные или права доступа тестового пользователя."
        )

    if auth_skipped:
        _log(f"Пропущено (нет доступа): {len(auth_skipped)} маршрутов из {len(routes)}")

    return screenshots


_LOGIN_PATH_KEYWORDS = ('login', 'sign-in', 'signin', 'logout', '/auth/', '/auth$')
_LOGIN_SUBMIT_TEXTS = ('войти', 'вход', 'sign in', 'log in', 'login', 'submit', 'continue')


def _is_login_redirect(original_url: str, final_url: str) -> bool:
    """
    True если произошёл редирект на страницу авторизации.
    Проверяет только PATH финального URL, а не hostname (избегает ложного
    срабатывания на 'authors.example' или 'authentication-service.com').
    """
    try:
        from urllib.parse import urlparse
        orig = urlparse(original_url)
        final = urlparse(final_url)
        # Если hostname изменился — возможно редирект на SSO/auth-сервис
        if orig.netloc and final.netloc and orig.netloc != final.netloc:
            final_path = (final.netloc + final.path).lower()
        else:
            final_path = final.path.lower()
        return any(kw in final_path for kw in _LOGIN_PATH_KEYWORDS)
    except Exception:
        return False


def _page_has_login_form(page) -> bool:
    """
    True если страница показывает форму входа (не форму смены пароля/настроек).
    Критерии: видимый password-input И рядом submit-кнопка с текстом «войти»/«sign in».
    Обычная страница настроек с полем пароля не считается формой входа.
    """
    try:
        pwd_fields = page.locator('input[type="password"]')
        if not pwd_fields.first.is_visible(timeout=500):
            return False
        # Ищем кнопку/submit с login-текстом в той же форме или на странице
        for text in _LOGIN_SUBMIT_TEXTS:
            btn = page.locator(
                f'button:has-text("{text}"), input[type="submit"][value*="{text}"]'
            ).first
            if btn.is_visible(timeout=200):
                return True
        return False
    except Exception:
        return False


def _do_login(page, base_url, login, password) -> bool:
    """
    Пытается войти в приложение через форму логина.
    Возвращает True если авторизация выполнена, False если не удалась.
    """
    # Пробуем сначала корневой URL (inline auth типа WithAuth HOC),
    # затем стандартные login-страницы
    login_urls = [
        base_url + '/',
        f"{base_url}/login",
        f"{base_url}/sign-in",
        f"{base_url}/signin",
        f"{base_url}/auth/login",
        f"{base_url}/auth",
    ]

    login_selectors = [
        'input[name="username"]',
        'input[name="login"]',
        'input[type="email"]',
        'input[name="email"]',
        'input[placeholder*="mail" i]',
        'input[placeholder*="логин" i]',
        'input[placeholder*="email" i]',
        'input[placeholder*="user" i]',
        'input[type="text"]',
    ]
    password_selectors = [
        'input[type="password"]',
    ]
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Войти")',
        'button:has-text("Вход")',
        'button:has-text("Sign in")',
        'button:has-text("Login")',
        'button:has-text("Войти в систему")',
        'button:has-text("Авторизоваться")',
    ]

    for login_url in login_urls:
        try:
            page.goto(login_url, wait_until='networkidle', timeout=15000)
            time.sleep(1)

            login_field = None
            for sel in login_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=800):
                        login_field = el
                        break
                except Exception:
                    continue

            password_field = None
            for sel in password_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=800):
                        password_field = el
                        break
                except Exception:
                    continue

            if not login_field or not password_field:
                continue

            login_field.fill(login)
            password_field.fill(password)

            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=800):
                        btn.click()
                        page.wait_for_load_state('networkidle', timeout=15000)
                        time.sleep(1)
                        # Проверяем что вошли: форма должна исчезнуть
                        if not _page_has_login_form(page):
                            _log(f"Авторизация выполнена через {login_url}")
                            return True
                        else:
                            _log(f"Форма логина осталась после отправки — неверные данные или ошибка")
                            return False
                except Exception:
                    continue

        except Exception as e:
            _log(f"Не удалось войти через {login_url}: {e}")
            continue

    _log("Авторизация не удалась — форма входа не найдена")
    return False


def _wait_for_port(port, timeout=120, process=None):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Dev-сервер завершился с кодом {process.returncode}")
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
            return
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"React-сервер не запустился за {timeout} секунд")


def _safe_filename(name):
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
    return safe.lower()[:50]


def _uses_hash_router(source_path) -> bool:
    """
    Определяет, использует ли проект HashRouter (URL вида /#/path).

    Сканирует только известные директории исходников (src/, app/, pages/)
    и корневые файлы. Намеренно НЕ использует rglob от корня проекта, чтобы
    не обходить node_modules — после npm install это могут быть сотни тысяч
    файлов, что на Windows занимает несколько минут.
    """
    source = Path(source_path)
    # Директории с исходниками, которые стоит проверить
    candidate_dirs = [
        source / 'src',
        source / 'app',
        source / 'pages',
    ]
    # Добавляем корень — только файлы верхнего уровня (не рекурсивно)
    candidates = list(source.glob('*.jsx')) + list(source.glob('*.tsx')) \
               + list(source.glob('*.js')) + list(source.glob('*.ts'))
    for d in candidate_dirs:
        if d.is_dir():
            for ext in ('*.jsx', '*.tsx', '*.js', '*.ts'):
                candidates.extend(d.rglob(ext))

    for f in candidates:
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        if 'HashRouter' in content:
            return True
    return False
