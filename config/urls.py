from django.contrib import admin
from django.urls import path
from core import views

# Импортируем login_required из django.contrib.auth.decorators
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('admin/', admin.site.urls),

    # Авторизация
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Основные страницы
    path('', views.home, name='home'),
    path('settings/', views.account_settings, name='settings'),
    path('history/', views.history, name='history'),

    # API
    path('api/projects/create/', views.create_project_api, name='create_project_api'),
    path('api/profile/update/', views.update_profile_api, name='update_profile_api'),
    path('api/change-password/', views.change_password_api, name='change_password_api'),
]