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
)

from .services.jsx_parser import (
    parse_jsx_instructions,
    find_component_file,
)

from .services.instruction_generator import generate_instructions_with_yandex
from .services.document_builder import build_document_pages
from .services.source_loader import prepare_project_source
from .services.screenshot_service import take_route_screenshots


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
    generations = Generation.objects.filter(user=request.user).order_by('-created_at')

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

        project = Project.objects.create(
            name=name,
            description=f"Репозиторий: {repo_url}\nВетка: {branch}",
            instructions_count=0,
            user=request.user,
            repo_url=repo_url,
            react_archive=react_archive,
            branch=branch,
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
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def update_profile_api(request):
    """API для обновления профиля"""
    try:
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)

        # Если нужно сохранить дополнительные поля
        if hasattr(user, 'profile'):
            user.profile.phone = request.POST.get('phone', '')
            user.profile.company = request.POST.get('company', '')
            user.profile.bio = request.POST.get('bio', '')
            user.profile.save()

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

    print("\n=== INSTRUCTIONS ===")

    for instruction in instructions:
        print(instruction)

    print("====================\n")

    document_pages = build_document_pages(
        project,
        instructions,
    )

    print("\n=== DOCUMENT PAGES ===")

    for page in document_pages:
        print(page)

    print("======================")

    context = {
        'project': project,
        'project_generations': project_generations,
        'generations_count': project_generations.count(),
        'last_generation': last_generation,
        'active_menu': 'projects',
        'instructions': instructions,
        'document_pages': document_pages,
    }

    return render(request, 'core/project_detail.html', context)


def _take_screenshots_background(generation_id, source_path, cleanup_path, routes, project_id):
    """Делает скриншоты в фоновом потоке и обновляет генерацию."""
    import django
    try:
        screenshots = take_route_screenshots(source_path, routes, project_id)
        generation = Generation.objects.get(id=generation_id)
        data = generation.instruction_data or []
        for item in data:
            item['screenshot'] = screenshots.get(item['path'])
        generation.instruction_data = data
        generation.status = 'completed'
        generation.completed_at = timezone.now()
        generation.duration_seconds = int((generation.completed_at - generation.created_at).total_seconds())
        generation.save()
        print(f"Скриншоты готовы: {len(screenshots)} шт.")
    except Exception as e:
        print(f"Ошибка скриншотов в фоне: {e}")
        try:
            generation = Generation.objects.get(id=generation_id)
            generation.status = 'failed'
            generation.error_message = str(e)
            generation.completed_at = timezone.now()
            generation.duration_seconds = int((generation.completed_at - generation.created_at).total_seconds())
            generation.save()
        except Exception:
            pass
    finally:
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
            routes_path = Path(source_path) / "src" / "routes.js"

            if not routes_path.exists():
                raise Exception("Файл routes.js не найден в архиве")

            routes = parse_routes(routes_path)
            imports = parse_component_imports(routes_path)

            instruction_data = []

            for route in routes:
                route_name = route.get('name') or 'Раздел'
                route_path = route.get('path') or '/'
                component_key = route.get('component') or route_name

                component_file = find_component_file(
                    source_path,
                    imports.get(component_key, '')
                )

                if component_file and Path(component_file).exists():
                    jsx_content = Path(component_file).read_text(encoding='utf-8', errors='ignore')
                else:
                    jsx_content = ''

                steps = generate_instructions_with_yandex(route_name, route_path, jsx_content)

                instruction_data.append({
                    'name': route_name,
                    'path': route_path,
                    'instructions': steps,
                    'screenshot': None,
                })

            generation = Generation.objects.create(
                project=project,
                user=request.user,
                commit_hash=f"gen_{int(timezone.now().timestamp())}",
                commit_message=f"Генерация инструкции для {project.name}",
                components_count=len(instruction_data),
                instruction_data=instruction_data,
                status='processing'
            )

            project.instructions_count = len(instruction_data)
            project.save()

            # Запускаем скриншоты в фоне
            import threading
            thread = threading.Thread(
                target=_take_screenshots_background,
                args=(generation.id, source_path, cleanup_path, routes, project.id),
                daemon=True,
            )
            thread.start()

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

@login_required
def generation_status_api(request, generation_id):
    """Возвращает статус скриншотов для генерации."""
    generation = get_object_or_404(Generation, id=generation_id, user=request.user)
    data = generation.instruction_data or []
    screenshots_done = any(item.get('screenshot') for item in data)
    return JsonResponse({'screenshots_done': screenshots_done})


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