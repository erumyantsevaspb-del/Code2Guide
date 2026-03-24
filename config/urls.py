from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('settings/', views.account_settings, name='settings'),
    path('api/projects/create/', views.create_project_api, name='create_project_api'),
    path('api/profile/update/', views.update_profile_api, name='update_profile_api'),
    path('api/change-password/', views.change_password_api, name='change_password_api'),
]