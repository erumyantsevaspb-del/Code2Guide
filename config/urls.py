from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

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
    path('project/<int:project_id>/', views.project_detail, name='project_detail'),  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
    path(
        'project/<int:project_id>/preview/',
        views.preview_document,
        name='preview_document',
    ),


    # API
    path('api/projects/create/', views.create_project_api, name='create_project_api'),
    path('api/projects/<int:project_id>/generate/', views.generate_instruction_api, name='generate_instruction'),
    path('api/profile/update/', views.update_profile_api, name='update_profile_api'),
    path('api/change-password/', views.change_password_api, name='change_password_api'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)