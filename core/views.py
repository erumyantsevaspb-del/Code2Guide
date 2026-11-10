from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Project, Generation
import random
import shutil
from pathlib import Path

from .services.react_parser import (
    parse_routes,
    parse_component_imports,
    parse_react_admin_routes,
    parse_nextjs_routes,
    parse_nextjs_pages_routes,
    parse_routepath_routes,
    parse_jsx_routes,
    parse_browser_router_routes,
    parse_distributed_router_files,
    parse_paths_config_routes,
    parse_remix_flat_routes,
    parse_component_pages_fallback,
)

from .services.jsx_parser import (
    parse_jsx_instructions,
    find_component_file,
    find_component_by_name,
)

from .services.instruction_generator import generate_instructions_with_yandex
from .services.backend_parser import parse_backend_zip, get_route_context
from .services.document_builder import build_document_pages
from .services.source_loader import prepare_project_source
from .services.screenshot_service import take_route_screenshots
from .services.experiment import get_experiment_meta
from .services.route_config_parser import parse_router_config_full, _read_tsconfig_aliases
from .services.import_traverser import collect_ui_from_component
from .constants import SCREENSHOT_WATCHDOG_TIMEOUT, SCREENSHOT_ZOMBIE_TIMEOUT, FRONTEND_POLL_TIMEOUT_MS


def register_view(request):
    """Регистрация нового пользователя"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно!')
            return redirect('home')
        else:
            messages.error(request, 'Ошибка регистрации. Проверьте введённые данные.')
    else:
        form = UserCreationForm()

    return render(request, 'core/auth/register.html', {'form': form})


def login_view(request):
    """Вход пользователя"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Добро пожаловать, {username}!')
                return redirect('home')
        messages.error(request, 'Неверное имя пользователя или пароль.')

    return render(request, 'core/auth/login.html')


def logout_view(request):
    """Выход пользователя"""
    logout(request)
    messages.success(request, 'Вы вышли из системы.')
    return redirect('login')


@login_required
def home(request):
    """Главная страница - Мои проекты (только проекты пользователя)"""
    projects = Project.objects.filter(user=request.user)
    recent_generations = Generation.objects.filter(user=request.user)[:10]

    user_data = {
        'name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    context = {
        'projects': projects,
        'recent_generations': recent_generations,
        'user': user_data,
        'active_menu': 'projects',
    }

    return render(request, 'core/home.html', context)


@login_required
def account_settings(request):
    """Страница настроек аккаунта"""
    user_data = {
        'name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    menu_items = [
        {'id': 'profile', 'label': 'Профиль', 'icon': 'fas fa-user', 'danger': False},
        {'id': 'security', 'label': 'Безопасность', 'icon': 'fas fa-shield-alt', 'danger': False},
        {'id': 'notifications', 'label': 'Уведомления', 'icon': 'fas fa-bell', 'danger': False},
        {'id': 'billing', 'label': 'Платежи и подписка', 'icon': 'fas fa-credit-card', 'danger': False},
        {'id': 'team', 'label': 'Команда', 'icon': 'fas fa-users', 'danger': False},
        {'id': 'api', 'label': 'API и интеграции', 'icon': 'fas fa-key', 'danger': False},
        {'id': 'delete', 'label': 'Удаление аккаунта', 'icon': 'fas fa-trash-alt', 'danger': True},
    ]

    context = {
        'user': user_data,
        'menu_items': menu_items,
        'active_menu': 'settings',
        'active_section': 'profile',
    }

    return render(request, 'core/account_settings.html', context)


@login_required
def history(request):
    """Страница истории генераций"""
    generations = Generation.objects.filter(user=request.user).select_related('project').order_by('-created_at')

    user_data = {
        'name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
    }

    context = {
        'generations': generations,
        'user': user_data,
        'active_menu': 'history',
    }

    return render(request, 'core/history.html', context)


@login_required
@require_POST
def delete_project_api(request, project_id):
    """Удаление проекта и всех его генераций"""
    project = get_object_or_404(Project, id=project_id, user=request.user)
    project.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def update_project_api(request, project_id):
    """Обновление настроек проекта (URL, логин, пароль для скриншотов)."""
    project = get_object_or_404(Project, id=project_id, user=request.user)
    app_url = request.POST.get('app_url', '').strip()
    if app_url and not app_url.startswith(('http://', 'https://')):
        app_url = 'https://' + app_url
    project.app_url = app_url
    project.app_login = request.POST.get('app_login', '').strip()
    # Пароль обновляем только если передан (не пустой)
    new_password = request.POST.get('app_password', '').strip()
    if new_password:
        project.app_password = new_password
    project.nx_app_name = request.POST.get('nx_app_name', '').strip()
    project.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def create_project_api(request):
    """API для создания проекта (привязан к пользователю)"""
    try:
        name = request.POST.get('name')
        repo_url = request.POST.get('repo_url')
        branch = request.POST.get('branch', 'main')
        react_archive = request.FILES.get('react_archive')

        if not name:
            return JsonResponse(
                {'error': 'Название проекта обязательно'},
                status=400
            )

        if not repo_url and not react_archive:
            return JsonResponse(
                {'error': 'Укажите URL репозитория или загрузите ZIP архив'},
                status=400
            )

        if react_archive:
            import zipfile as _zf
            if not react_archive.name.lower().endswith('.zip'):
                return JsonResponse(
                    {'error': 'Файл должен быть ZIP-архивом (.zip)'},
                    status=400
                )
            try:
                if not _zf.is_zipfile(react_archive):
                    return JsonResponse(
                        {'error': 'Загруженный файл не является корректным ZIP-архивом'},
                        status=400
                    )
            finally:
                react_archive.seek(0)

        import secrets
        business_context = request.POST.get('business_context', '').strip()

        backend_archive = request.FILES.get('backend_archive')

        project = Project.objects.create(
            name=name,
            description=f"Репозиторий: {repo_url}\nВетка: {branch}",
            business_context=business_context,
            instructions_count=0,
            user=request.user,
            repo_url=repo_url,
            react_archive=react_archive,
            backend_archive=backend_archive,
            branch=branch,
            api_token=secrets.token_hex(24),
        )

        return JsonResponse({
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'created_at': project.created_at.strftime('%d %B %Y'),
                'instructions_count': project.instructions_count
            }
        })

    except Exception as e:
        _views_logger.error(f"create_project_api error: {e}", exc_info=True)
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
@require_POST
def update_profile_api(request):
    """API для обновления профиля"""
    try:
        user = request.user

        # Обновляем только переданные поля, не затираем остальные
        if 'first_name' in request.POST:
            user.first_name = request.POST['first_name'].strip()
        if 'last_name' in request.POST:
            user.last_name = request.POST['last_name'].strip()

        # Дополнительные поля модели User (если есть)
        for field in ('phone', 'company', 'position'):
            if field in request.POST and hasattr(user, field):
                setattr(user, field, request.POST[field].strip())

        # Аватар
        if 'avatar' in request.FILES and hasattr(user, 'avatar'):
            user.avatar = request.FILES['avatar']

        user.save()
        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def change_password_api(request):
    """API для смены пароля"""
    try:
        user = request.user
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')

        if not user.check_password(current_password):
            return JsonResponse({'error': 'Неверный текущий пароль'}, status=400)

        user.set_password(new_password)
        user.save()

        # Обновляем сессию, чтобы пользователь не вышел
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def project_detail(request, project_id):
    """Страница деталей проекта"""
    project = get_object_or_404(Project, id=project_id, user=request.user)
    project_generations = Generation.objects.filter(project=project).order_by('-created_at')

    last_generation = project_generations.first()

    instructions = (
        last_generation.instruction_data
        if last_generation
        else []
    )

    document_pages = build_document_pages(
        project,
        instructions,
    )

    # NX: детектируем monorepo и список приложений для UI
    # Приоритет: nx_detected_apps из БД (заполняется при первой генерации).
    # Если ещё пусто — быстрый детект через ZIP (только package.json, без распаковки).
    _nx_detected = list(project.nx_detected_apps or [])
    _is_nx_project = bool(_nx_detected)

    if not _is_nx_project and project.react_archive:
        try:
            import json as _json_ctx
            import zipfile as _zf_ctx
            from pathlib import Path as _Path_ctx
            from django.conf import settings as _settings_ctx
            _zip = _Path_ctx(_settings_ctx.MEDIA_ROOT) / str(project.react_archive)
            if _zip.exists():
                with _zf_ctx.ZipFile(str(_zip)) as _z:
                    for _n in _z.namelist():
                        _parts = _n.strip('/').split('/')
                        if len(_parts) <= 2 and _parts[-1] == 'package.json':
                            try:
                                _raw = _z.read(_n).decode('utf-8', errors='ignore')
                                _scripts = _json_ctx.loads(_raw).get('scripts', {})
                                _dev = _scripts.get('dev', _scripts.get('start', ''))
                                if 'nx ' in _dev or 'nx run' in _dev:
                                    _is_nx_project = True
                            except Exception:
                                pass
                            break
        except Exception:
            pass

    context = {
        'project': project,
        'project_generations': project_generations,
        'generations_count': project_generations.count(),
        'last_generation': last_generation,
        'active_menu': 'projects',
        'instructions': instructions,
        'document_pages': document_pages,
        'frontend_poll_timeout_ms': FRONTEND_POLL_TIMEOUT_MS,
        'is_nx_project': _is_nx_project,
        'nx_detected_apps': _nx_detected,
    }

    return render(request, 'core/project_detail.html', context)


import logging as _views_logging
_views_logger = _views_logging.getLogger(__name__)


def _save_experiment_result_safe(generation):
    """Сохраняет результат в experiment_results/. Не бросает исключений."""
    try:
        from .services.experiment_storage import save_experiment_result
        path = save_experiment_result(generation)
        _views_logger.debug("Результат эксперимента сохранён: %s", path)
    except Exception as ex:
        _views_logger.warning("Не удалось сохранить результат эксперимента: %s", ex)


def _force_complete_generation(generation_id, reason):
    """Принудительно переводит генерацию из processing в failed с диагностикой.
    Вызывается защитным таймером при зависании фонового потока.
    Статус failed, а не completed: таймаут — это сбой, пользователь должен видеть ошибку."""
    try:
        from django import db as _db
        _db.close_old_connections()
        gen = Generation.objects.get(id=generation_id)
        if gen.status == 'processing':
            gen.status = 'failed'
            gen.error_message = f"Таймаут генерации: {reason}"
            gen.completed_at = timezone.now()
            gen.duration_seconds = int((gen.completed_at - gen.created_at).total_seconds())
            gen.save()
            _views_logger.warning("[WATCHDOG] Generation %s завершена с ошибкой таймаута: %s", generation_id, reason)
            _save_experiment_result_safe(gen)
    except Exception as e:
        _views_logger.error("[WATCHDOG] Не удалось завершить generation %s: %s", generation_id, e)


def _take_screenshots_background(generation_id, source_path, cleanup_path, routes, project_id,
                                  app_url=None, app_login=None, app_password=None,
                                  nx_app_name=None):
    """Делает скриншоты в фоновом потоке и обновляет генерацию."""
    import sys as _sys_bg
    import time as _time_bg
    import threading as _threading_bg
    from datetime import datetime as _dt_bg
    from pathlib import Path as _Path_bg

    # Лог-файл для этого потока: изолирует диагностику от stderr.
    # На Windows запись в stderr с flush=True блокируется когда терминал
    # находится в режиме выделения (Quick Edit Mode) — генерация зависает.
    from django.conf import settings as _settings_bg
    _bg_log_dir = _Path_bg(_settings_bg.MEDIA_ROOT) / 'screenshots' / str(project_id)
    try:
        _bg_log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _bg_log_path = str(_bg_log_dir / f'gen_{generation_id}.log')

    # Подключаем _tls screenshot_service к файлу ДО любых вызовов _log/_diag_bg
    from core.services import screenshot_service as _ss_module
    _ss_module._tls.log_file = _bg_log_path

    def _diag_bg(msg):
        line = f"[{_dt_bg.now().strftime('%H:%M:%S.%f')[:12]}] [DIAG] {msg}"
        try:
            with open(_bg_log_path, 'a', encoding='utf-8') as _f:
                _f.write(line + '\n')
        except Exception:
            pass

    _t_bg_start = _time_bg.perf_counter()
    _diag_bg(f"background thread started, generation_id={generation_id}")

    # Защитный таймер: если поток завис дольше SCREENSHOT_WATCHDOG_TIMEOUT — принудительно завершаем.
    # Таймер не убивает поток (в Python нельзя), но снимает статус processing из БД.
    _watchdog = _threading_bg.Timer(
        SCREENSHOT_WATCHDOG_TIMEOUT,
        _force_complete_generation,
        args=(generation_id, f"защитный таймаут {SCREENSHOT_WATCHDOG_TIMEOUT}с истёк"),
    )
    _watchdog.daemon = True
    _watchdog.start()
    # ── Блок 1: только получение скриншотов ─────────────────────────
    screenshot_exc = None
    screenshots = {}

    # Определяем режим скриншотов.
    # Приоритет: 1) внешний URL, 2) NX-приложение, 3) локальный запуск обычного React.
    _early_skip_reason = None
    _resolved_nx_app = None  # имя NX-приложения, которое будем запускать

    # Детектируем NX monorepo по корневому package.json
    _is_nx_bg = False
    if source_path and not (app_url and app_login and app_password):
        try:
            import json as _json_bg
            _pkg = _Path_bg(source_path) / 'package.json'
            _dev_cmd = _json_bg.loads(_pkg.read_text(encoding='utf-8', errors='ignore')).get('scripts', {}).get(
                'dev', _json_bg.loads(_pkg.read_text(encoding='utf-8', errors='ignore')).get('scripts', {}).get(
                    'start', ''))
            if 'nx ' in _dev_cmd or 'nx run' in _dev_cmd:
                _is_nx_bg = True
        except Exception:
            pass

    if _is_nx_bg and not (app_url and app_login and app_password):
        # NX: определяем какое приложение запускать
        from core.services.screenshot_service import find_nx_serve_apps as _find_nx_apps
        _nx_apps = _find_nx_apps(source_path)

        # Сохраняем обнаруженные приложения в Project для отображения в UI
        try:
            from django.db import close_old_connections as _close_conn_nx
            _close_conn_nx()
            _proj_for_nx = Project.objects.get(id=project_id)
            if list(_proj_for_nx.nx_detected_apps) != _nx_apps:
                _proj_for_nx.nx_detected_apps = _nx_apps
                _proj_for_nx.save(update_fields=['nx_detected_apps'])
                _diag_bg(f"NX: сохранены detected_apps={_nx_apps}")
        except Exception as _nx_save_err:
            _diag_bg(f"NX: не удалось сохранить detected_apps: {_nx_save_err}")

        if nx_app_name and nx_app_name in _nx_apps:
            # Явно задан и существует — используем
            _resolved_nx_app = nx_app_name
            _diag_bg(f"NX: используем указанное приложение '{_resolved_nx_app}'")
        elif nx_app_name and _nx_apps and nx_app_name not in _nx_apps:
            # Задан, но не найден среди serve-приложений
            _early_skip_reason = (
                f"NX: приложение '{nx_app_name}' не найдено. "
                f"Доступные: {', '.join(_nx_apps)}. Выберите приложение в настройках проекта."
            )
        elif len(_nx_apps) == 1:
            # Ровно одно serve-приложение — выбираем автоматически
            _resolved_nx_app = _nx_apps[0]
            _diag_bg(f"NX: автовыбор единственного приложения '{_resolved_nx_app}'")
        elif len(_nx_apps) > 1:
            # Несколько приложений — нужен явный выбор пользователя
            _early_skip_reason = (
                f"Для скриншотов выберите приложение в настройках проекта. "
                f"Доступные: {', '.join(_nx_apps)}."
            )
        else:
            # Нет serve-приложений в apps/
            _early_skip_reason = (
                "NX monorepo: не найдено приложений с target 'serve' в apps/. "
                "Укажите URL работающего приложения в настройках проекта."
            )

    # Краткое прогресс-сообщение: записываем текущий этап до старта (не блокирует)
    try:
        from django.db import close_old_connections as _close_conn
        _close_conn()
        _g_progress = Generation.objects.get(id=generation_id)
        if _g_progress.status == 'processing':
            if _early_skip_reason:
                _g_progress.error_message = f"Скриншоты: {_early_skip_reason[:120]}"
            elif _resolved_nx_app:
                _g_progress.error_message = f"Скриншоты: NX serve {_resolved_nx_app} ({len(routes)} маршрутов)…"
            elif app_url and app_login and app_password:
                _g_progress.error_message = f"Создаём скриншоты ({len(routes)} маршрутов, с авторизацией)…"
            else:
                _g_progress.error_message = f"Создаём скриншоты ({len(routes)} маршрутов, локальный запуск)…"
            _g_progress.save(update_fields=['error_message'])
    except Exception:
        pass

    if _early_skip_reason:
        screenshot_exc = RuntimeError(_early_skip_reason)
        _diag_bg(f"Ранний выход (NX): {_early_skip_reason}")
    else:
        try:
            if app_url and app_login and app_password:
                from core.services.screenshot_service import take_screenshots_with_credentials
                screenshots = take_screenshots_with_credentials(app_url, app_login, app_password, routes, project_id)
            elif _resolved_nx_app:
                from core.services.screenshot_service import take_nx_screenshots as _take_nx
                screenshots = _take_nx(source_path, _resolved_nx_app, routes, project_id)
            else:
                screenshots = take_route_screenshots(source_path, routes, project_id)
        except Exception as e:
            screenshot_exc = e
            _diag_bg(f"Ошибка скриншотов: {e}")

    # ── Блок 2: обновление Generation ───────────────────────────────
    # Сбой save() здесь не попадает в классификатор скриншотов.
    # При неудаче БД запись остаётся в 'processing' — это честно и видно в логах.
    try:
        generation = Generation.objects.get(id=generation_id)

        if screenshot_exc is None and screenshots:
            # Скриншоты получены (словарь {path: {file, status, reason, ...}})
            data = generation.instruction_data or []
            real_count = 0
            for item in data:
                entry = screenshots.get(item['path'])
                if entry is None:
                    # Маршрут не был обработан совсем
                    item['screenshot'] = None
                    item['screenshot_status'] = 'unavailable'
                    item['screenshot_reason'] = 'Маршрут не обработан'
                    item['screenshot_meta'] = {}
                elif isinstance(entry, dict):
                    item['screenshot'] = entry.get('file')
                    item['screenshot_status'] = entry.get('status', 'ok')
                    item['screenshot_reason'] = entry.get('reason', '')
                    item['screenshot_meta'] = {
                        'final_url': entry.get('final_url', ''),
                        'title': entry.get('title', ''),
                        'h1': entry.get('h1', ''),
                    }
                    if entry.get('file'):
                        real_count += 1
                else:
                    # backward-compat: строка (старый формат)
                    item['screenshot'] = entry
                    item['screenshot_status'] = 'ok'
                    item['screenshot_reason'] = ''
                    item['screenshot_meta'] = {}
                    real_count += 1
            generation.instruction_data = data
            generation.status = 'completed'
            generation.error_message = ''
            _diag_bg(f"Скриншоты готовы: {real_count} файлов из {len(screenshots)} маршрутов.")
        elif screenshot_exc is None and not screenshots:
            # take_route_screenshots вернул пустой словарь без исключения
            generation.status = 'completed_without_screenshots'
            generation.error_message = 'Скриншоты не созданы: сервер запустился, но ни один маршрут не открылся.'
        else:
            # Скриншоты не получены — классифицируем причину
            # TimeoutError всегда ожидаем (сервер не успел запуститься).
            # RuntimeError проверяем по тексту — он может быть поднят по любой причине.
            is_expected = isinstance(screenshot_exc, TimeoutError)
            if not is_expected:
                err_lower = str(screenshot_exc).lower()
                expected_keywords = (
                    'nx monorepo', 'не поддерживается', 'timedout', 'timeout',
                    'timed out', 'не запустился', 'dev-сервер завершился',
                    'npm install завершился', 'нет подходящего скрипта',
                    'все маршруты не открылись',
                    'авторизация не выполнена', 'недоступны после авторизации',
                    # NX: выбор приложения
                    'выберите nx-приложение', 'не найдено среди serve',
                    'не найдено приложений с target', 'для скриншотов выберите',
                    'исправьте имя в настройках',
                    'nx: приложение', 'доступные:', 'выберите приложение в настройках',
                    # Ошибка установки зависимостей (yarn/pnpm/npm + нестандартный registry)
                    'yarn install завершился', 'corepack yarn install завершился',
                    'pnpm install завершился',
                    'нестандартный registry', 'pnpm не поддерживается',
                    'yarn не установлен',
                    'не удалось установить зависимости',
                )
                is_expected = any(k in err_lower for k in expected_keywords)

            if is_expected:
                # Ожидаемая причина — документ сформирован, скриншоты пропущены намеренно
                generation.status = 'completed_without_screenshots'
                generation.error_message = f"Скриншоты недоступны: {screenshot_exc}"
            else:
                # Неожиданная ошибка скриншотов — независимо от наличия instruction_data
                # статус failed, чтобы пользователь видел реальную причину
                generation.status = 'failed'
                generation.error_message = f"Ошибка скриншотов: {screenshot_exc}"

        generation.completed_at = timezone.now()
        generation.duration_seconds = int((generation.completed_at - generation.created_at).total_seconds())
        generation.save()
        if generation.status in ('completed', 'completed_without_screenshots'):
            _save_experiment_result_safe(generation)

    except Exception as save_exc:
        _views_logger.error("Критическая ошибка: не удалось обновить Generation %s: %s", generation_id, save_exc)

    finally:
        _watchdog.cancel()
        shutil.rmtree(cleanup_path, ignore_errors=True)


@login_required
@require_POST
def generate_instruction_api(request, project_id):
    """API для генерации инструкции"""
    try:
        project = get_object_or_404(
            Project,
            id=project_id,
            user=request.user
        )

        # Получаем исходники (ZIP или репозиторий)
        source_path, cleanup_path = prepare_project_source(project)

        try:
            # Парсим бэкенд если загружен
            backend_context = {}
            if project.backend_archive:
                backend_zip_path = project.backend_archive.path
                backend_context = parse_backend_zip(backend_zip_path)

            routes_path = Path(source_path) / "src" / "routes.js"

            approximate_routes = False
            if routes_path.exists():
                # CoreUI: src/routes.js
                routes = parse_routes(routes_path)
                imports = parse_component_imports(routes_path)
            elif (Path(source_path) / 'next.config.js').exists() or (Path(source_path) / 'next.config.ts').exists() or (Path(source_path) / 'next.config.mjs').exists():
                # Next.js: сначала App Router (app/page.tsx), затем Pages Router (pages/)
                routes = parse_nextjs_routes(source_path)
                imports = {}
                if not routes:
                    routes = parse_nextjs_pages_routes(source_path)
                if not routes:
                    raise Exception("Next.js проект найден, но страницы не обнаружены (проверьте app/ или pages/)")
            else:
                imports = {}
                # RoutePath: кастомный TS роутер (включая computed keys)
                routes = parse_routepath_routes(source_path)
                if not routes:
                    # React Admin: ищем <Resource name="...">
                    routes = parse_react_admin_routes(source_path)
                if not routes:
                    # React Router v6 JSX + v4/v5 component= + react-router v7
                    routes = parse_jsx_routes(source_path)
                if not routes:
                    # Распределённые *.router.tsx / *.router.ts файлы (e.g. React Admin Dashboard)
                    routes = parse_distributed_router_files(source_path)
                if not routes:
                    # createBrowserRouter([{path, Component/element}]) — React Router v6/v7
                    routes = parse_browser_router_routes(source_path)
                if not routes:
                    # Файлы конфигурации путей — paths.ts (e.g. Bulletproof React monorepo)
                    routes = parse_paths_config_routes(source_path)
                if not routes:
                    # remix-flat-routes: структура app/routes/ (React Router v7 / Remix)
                    routes = parse_remix_flat_routes(source_path)
                if not routes:
                    # Эвристический фолбэк: src/pages/, src/views/, src/screens/
                    routes = parse_component_pages_fallback(source_path)
                    if routes:
                        approximate_routes = True
                if not routes:
                    raise Exception("Не удалось найти маршруты. Поддерживаются: CoreUI (routes.js), React Admin (<Resource>), Next.js (app/ или pages/), RoutePath (router.ts), React Router v4-v7 JSX, createBrowserRouter, distributed *.router.tsx, paths.ts config, remix-flat-routes")

            instruction_data = []

            # Pre-pass: router.config.tsx → точный маппинг route_key -> file
            router_config_map = parse_router_config_full(source_path)

            # Загружаем alias_map один раз для traversal импортов
            _traversal_alias_map = _read_tsconfig_aliases(Path(source_path))

            for route in routes:
                route_name = route.get('name') or 'Раздел'
                route_path = route.get('path') or '/'
                component_key = route.get('component') or route_name

                # 1. Поиск по явному пути из imports (CoreUI и аналоги)
                relative = imports.get(component_key, '')
                component_file = find_component_file(source_path, relative) if relative else None

                # 2. Router config: точный маппинг через router.config.tsx
                if not component_file and component_key:
                    config_path = router_config_map.get(component_key.lower())
                    if config_path and Path(config_path).exists():
                        component_file = config_path

                # 3. Если нет явного пути — ищем по имени компонента
                if not component_file and component_key:
                    component_file = find_component_by_name(source_path, component_key)

                component_found = bool(component_file and Path(component_file).exists())
                component_source = str(component_file) if component_found else ''

                if component_found:
                    jsx_content = Path(component_file).read_text(encoding='utf-8', errors='ignore')
                    merged_ast = collect_ui_from_component(
                        str(component_file),
                        source_path,
                        alias_map=_traversal_alias_map,
                        max_depth=3,
                    )
                else:
                    jsx_content = ''
                    merged_ast = None

                route_be_context = get_route_context(backend_context, route_path, route_name)
                steps = generate_instructions_with_yandex(
                    route_name, route_path, jsx_content, route_be_context,
                    ast_override=merged_ast,
                )

                instruction_data.append({
                    'name': route_name,
                    'path': route_path,
                    'instructions': steps,
                    'screenshot': None,
                    'component_found': component_found,
                    'component_source': component_source,
                })

            exp_meta = get_experiment_meta()
            generation = Generation.objects.create(
                project=project,
                user=request.user,
                commit_hash=f"gen_{int(timezone.now().timestamp())}",
                commit_message=f"Генерация инструкции для {project.name}",
                components_count=len(instruction_data),
                instruction_data=instruction_data,
                status='processing',
                algorithm_version=exp_meta['algorithm_version'],
                code_version=exp_meta['code_version'],
                error_message="Маршруты обнаружены приблизительно (эвристика по структуре файлов)" if approximate_routes else '',
            )

            project.instructions_count = len(instruction_data)
            project.save()

            # Запускаем скриншоты в фоне
            import threading
            import logging as _logging_http
            _http_logger = _logging_http.getLogger(__name__)
            _http_logger.debug("thread.start: до вызова, generation_id=%s", generation.id)
            thread = threading.Thread(
                target=_take_screenshots_background,
                args=(generation.id, source_path, cleanup_path, routes, project.id),
                kwargs={
                    'app_url': project.app_url or None,
                    'app_login': project.app_login or None,
                    'app_password': project.app_password or None,
                    'nx_app_name': project.nx_app_name or None,
                },
                daemon=True,
            )
            try:
                thread.start()
                _http_logger.debug("thread.start: запущен, generation_id=%s", generation.id)
            except Exception as thread_err:
                # Поток не запустился — документ уже сформирован, скриншоты не будут сделаны.
                # completed_without_screenshots: инструкции готовы, скриншоты пропущены.
                generation.status = 'completed_without_screenshots'
                generation.error_message = f"Скриншоты не запущены: {thread_err}"
                generation.completed_at = timezone.now()
                generation.duration_seconds = int(
                    (generation.completed_at - generation.created_at).total_seconds()
                )
                generation.save()
                shutil.rmtree(cleanup_path, ignore_errors=True)
                _save_experiment_result_safe(generation)

            return JsonResponse({
                'success': True,
                'generation': {
                    'id': generation.id,
                    'components': generation.components_count
                }
            })

        except Exception:
            shutil.rmtree(cleanup_path, ignore_errors=True)
            raise

    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@require_POST
def extension_ping_api(request):
    """Проверяет токен от расширения Chrome."""
    token = request.POST.get('token') or request.headers.get('X-Project-Token')
    if not token:
        return JsonResponse({'error': 'Токен обязателен'}, status=400)
    try:
        project = Project.objects.get(api_token=token)
        return JsonResponse({'success': True, 'project': project.name})
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Неверный токен'}, status=403)


@csrf_exempt
@require_POST
def extension_screenshot_api(request):
    """Принимает скриншот от расширения Chrome."""
    token = request.POST.get('token') or request.headers.get('X-Project-Token')
    page_url = request.POST.get('url', '')
    screenshot_file = request.FILES.get('screenshot')

    if not token:
        return JsonResponse({'error': 'Токен обязателен'}, status=400)
    if not screenshot_file:
        return JsonResponse({'error': 'Скриншот обязателен'}, status=400)

    try:
        project = Project.objects.get(api_token=token)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Неверный токен'}, status=403)

    # Сохраняем скриншот
    from urllib.parse import urlparse
    path = urlparse(page_url).path.rstrip('/') or '/'
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in path).strip('_') or 'home'

    screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots' / str(project.id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    file_path = screenshots_dir / f"{safe_name}.png"
    with open(file_path, 'wb') as f:
        for chunk in screenshot_file.chunks():
            f.write(chunk)

    rel_path = f"screenshots/{project.id}/{safe_name}.png"

    # Обновляем скриншот в последней генерации если есть
    last_gen = Generation.objects.filter(project=project).order_by('-created_at').first()
    if last_gen and last_gen.instruction_data:
        updated = False
        for item in last_gen.instruction_data:
            item_path = item.get('path', '').rstrip('/')
            if item_path == path or (not item_path and path == '/'):
                item['screenshot'] = rel_path
                updated = True
        if updated:
            last_gen.save()

    return JsonResponse({'success': True, 'saved': rel_path})


@login_required
def generation_status_api(request, generation_id):
    """Возвращает статус генерации."""
    generation = get_object_or_404(Generation, id=generation_id, user=request.user)

    # Зомби-восстановление: если генерация осталась в processing после рестарта сервера,
    # watchdog (daemon=True) мог не сработать. Принудительно завершаем через SCREENSHOT_ZOMBIE_TIMEOUT.
    if generation.status == 'processing' and generation.created_at:
        elapsed = (timezone.now() - generation.created_at).total_seconds()
        if elapsed > SCREENSHOT_ZOMBIE_TIMEOUT:
            generation.status = 'failed'
            generation.error_message = (
                f"Таймаут: генерация не завершилась за {elapsed / 60:.0f} мин "
                f"(фоновый процесс завершился без обновления статуса — возможно, сервер был перезапущен). "
                f"Запустите repair_stuck_generations или повторите генерацию."
            )
            generation.completed_at = timezone.now()
            generation.save(update_fields=['status', 'error_message', 'completed_at'])

    _FINAL_STATUSES = ('completed', 'completed_without_screenshots', 'failed')
    return JsonResponse({
        'status': generation.status,
        'screenshots_done': generation.status in _FINAL_STATUSES,
        'error_message': generation.error_message or '',
    })


@login_required
def preview_document(request, project_id):
    """Предпросмотр документа"""

    project = get_object_or_404(
        Project,
        id=project_id,
        user=request.user,
    )

    generation = (
        Generation.objects
        .filter(project=project)
        .order_by('-created_at')
        .first()
    )

    instructions = (
        generation.instruction_data
        if generation
        else []
    )

    document_pages = build_document_pages(
        project,
        instructions,
    )

    total_pages = len(document_pages)
    current_page = int(request.GET.get('page', 1))
    current_page = max(1, min(current_page, total_pages))
    current_page_data = document_pages[current_page - 1] if document_pages else {}

    context = {
        'project': project,
        'document_pages': document_pages,
        'current_page': current_page,
        'total_pages': total_pages,
        'current_page_data': current_page_data,
        'prev_page': current_page - 1 if current_page > 1 else None,
        'next_page': current_page + 1 if current_page < total_pages else None,
    }

    return render(
        request,
        'core/preview_document.html',
        context,
    )


@login_required
def pdf_print(request, project_id):
    """Страница предпросмотра перед печатью (вспомогательная)"""

    project = get_object_or_404(Project, id=project_id, user=request.user)
    generation = (
        Generation.objects.filter(project=project).order_by('-created_at').first()
    )
    instructions = generation.instruction_data if generation else []
    document_pages = build_document_pages(project, instructions)
    algorithm_version = generation.algorithm_version if generation else 'V0'

    return render(
        request,
        'core/pdf_print.html',
        {
            'project': project,
            'document_pages': document_pages,
            'algorithm_version': algorithm_version,
            'media_root': '/media/',
        },
    )


@login_required
def pdf_download(request, project_id):
    """Генерирует PDF через Playwright и отдаёт как файл для скачивания"""
    import tempfile
    from pathlib import Path
    from django.template.loader import render_to_string
    from django.http import HttpResponse, HttpResponseServerError

    project = get_object_or_404(Project, id=project_id, user=request.user)
    generation = (
        Generation.objects.filter(project=project).order_by('-created_at').first()
    )
    instructions = generation.instruction_data if generation else []
    document_pages = build_document_pages(project, instructions)
    algorithm_version = generation.algorithm_version if generation else 'V0'

    from django.conf import settings as django_settings
    media_root_path = Path(django_settings.MEDIA_ROOT).as_uri() + '/'

    html_content = render_to_string(
        'core/pdf_print.html',
        {
            'project': project,
            'document_pages': document_pages,
            'algorithm_version': algorithm_version,
            'media_root': media_root_path,
        },
        request=request,
    )

    try:
        from playwright.sync_api import sync_playwright

        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
            f.write(html_content)
            html_path = f.name

        pdf_path = html_path.replace('.html', '.pdf')

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f'file:///{html_path}')
            page.wait_for_load_state('networkidle', timeout=15000)
            page.pdf(
                path=pdf_path,
                format='A4',
                print_background=True,
                margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
            )
            browser.close()

        pdf_bytes = Path(pdf_path).read_bytes()
        Path(html_path).unlink(missing_ok=True)
        Path(pdf_path).unlink(missing_ok=True)

        safe_name = project.name.replace(' ', '_').replace('/', '_')
        filename = f'{safe_name}_{algorithm_version}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return HttpResponseServerError(f'Ошибка генерации PDF: {e}')