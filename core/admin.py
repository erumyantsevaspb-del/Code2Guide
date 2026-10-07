from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Project, Generation, Profile


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # Убираем is_active, так как его нет в модели
    list_display = ('name', 'user', 'created_at', 'instructions_count')
    list_filter = ('created_at', 'user')
    search_fields = ('name', 'user__username', 'description')
    date_hierarchy = 'created_at'
    list_editable = ('instructions_count',)
    readonly_fields = ('created_datetime', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'user', 'description', 'repo_url', 'branch')
        }),
        ('Статистика', {
            'fields': ('instructions_count',)
        }),
        ('Даты', {
            'fields': ('created_at', 'created_datetime', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Generation)
class GenerationAdmin(admin.ModelAdmin):
    list_display = ('id', 'commit_hash', 'user', 'project', 'created_at', 'components_count', 'status')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('commit_hash', 'commit_message', 'user__username', 'project__name')
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'project')

    fieldsets = (
        ('Информация о генерации', {
            'fields': ('project', 'user', 'status')
        }),
        ('GitHub', {
            'fields': ('commit_hash', 'commit_message')
        }),
        ('Результаты', {
            'fields': ('components_count', 'error_message')
        }),
        ('Даты', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'phone', 'email_notifications', 'telegram_notifications')
    list_filter = ('email_notifications', 'telegram_notifications')
    search_fields = ('user__username', 'user__email', 'company', 'phone')

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'company', 'position', 'bio')
        }),
        ('Контакты', {
            'fields': ('phone', 'telegram', 'github')
        }),
        ('Настройки', {
            'fields': ('email_notifications', 'telegram_notifications', 'timezone')
        }),
    )


# Расширяем стандартный UserAdmin, чтобы показывать профиль
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_company')
    list_filter = ('is_staff', 'is_active', 'date_joined')

    def get_company(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.company
        return '-'

    get_company.short_description = 'Компания'
    get_company.admin_order_field = 'profile__company'


# Перерегистрируем User с нашим кастомным админом
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)