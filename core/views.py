from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Project, Generation


def home(request):
    """
    Главная страница - Мои проекты
    """
    projects = Project.objects.all()
    recent_generations = Generation.objects.all()[:10]

    user_data = {
        'name': 'Моя компания',
        'email': 'admin@company.com',
    }

    context = {
        'projects': projects,
        'recent_generations': recent_generations,
        'user': user_data,
        'active_menu': 'projects',
    }

    return render(request, 'core/home.html', context)


def settings(request):
    """
    Страница настроек аккаунта
    """
    user_data = {
        'name': 'Моя компания',
        'email': 'admin@company.com',
    }

    context = {
        'user': user_data,
        'active_menu': 'settings',
    }

    return render(request, 'core/settings.html', context)


@require_POST
def create_project_api(request):
    """API для создания проекта"""
    try:
        name = request.POST.get('name')
        repo_url = request.POST.get('repo_url')
        branch = request.POST.get('branch', 'main')
        auto_generate = request.POST.get('auto_generate') == 'on'
        notifications = request.POST.get('notifications') == 'on'
        webhook_url = request.POST.get('webhook_url', '')

        if not name or not repo_url:
            return JsonResponse({'error': 'Название и URL репозитория обязательны'}, status=400)

        # Создаём проект
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