from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Project, Generation


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

        if not name or not repo_url:
            return JsonResponse({'error': 'Название и URL репозитория обязательны'}, status=400)

        project = Project.objects.create(
            name=name,
            description=f"Репозиторий: {repo_url}\nВетка: {branch}",
            instructions_count=0,
            user=request.user
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