from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('settings/', views.settings, name='settings'),
    path('api/projects/create/', views.create_project_api, name='create_project_api'),
]