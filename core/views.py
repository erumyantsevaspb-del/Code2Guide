from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Project, Generation


def home(request):
    """Главная страница - Мои проекты"""
    projects = Project.objects.all()
    recent_generations = Generation.objects.all()[:10]

    user_data = {
        'name': 'Моя компания',
        'email': 'admin@company.com',
        'first_name': 'Елена',
        'last_name': 'Румянцева',
        'company': 'Code2Guide',
        'phone': '+7 (999) 123-45-67',
        'position': '',
        'bio': '',
    }

    context = {
        'projects': projects,
        'recent_generations': recent_generations,
        'user': user_data,
        'active_menu': 'projects',
    }

    return render(request, 'core/home.html', context)


def account_settings(request):
    """Страница настроек аккаунта"""
    user_data = {
        'name': 'Моя компания',
        'email': 'admin@company.com',
        'first_name': 'Елена',
        'last_name': 'Румянцева',
        'company': 'Code2Guide',
        'phone': '+7 (999) 123-45-67',
        'position': '',
        'bio': '',
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


@require_POST
def create_project_api(request):
    """API для создания проекта"""
    try:
        name = request.POST.get('name')
        repo_url = request.POST.get('repo_url')
        branch = request.POST.get('branch', 'main')

        if not name or not repo_url:
            return JsonResponse({'error': 'Название и URL репозитория обязательны'}, status=400)

        project = Project.objects.create(
            name=name,
            description=f"Репозиторий: {repo_url}\nВетка: {branch}",
            instructions_count=0
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


@require_POST
def update_profile_api(request):
    """API для обновления профиля"""
    try:
        # Здесь будет логика обновления профиля
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def change_password_api(request):
    """API для смены пароля"""
    try:
        # Здесь будет логика смены пароля
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)