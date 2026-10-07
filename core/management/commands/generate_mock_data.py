from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from core.models import Project, Generation, Profile, Subscription


class Command(BaseCommand):
    help = 'Генерирует моковые данные для демонстрации работы приложения'

    def handle(self, *args, **kwargs):
        self.stdout.write('Начинаем генерацию моковых данных...')

        # 1. Создаём тестового пользователя
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Тестовый',
                'last_name': 'Пользователь',
                'is_active': True,
            }
        )

        if created:
            user.set_password('test123')
            user.save()
            self.stdout.write(self.style.SUCCESS('✅ Создан пользователь testuser (пароль: test123)'))
        else:
            self.stdout.write('ℹ️ Пользователь testuser уже существует')

        # Создаём профиль
        profile, created = Profile.objects.get_or_create(
            user=user,
            defaults={
                'company': 'ООО "Тестовая компания"',
                'phone': '+7 (999) 123-45-67',
                'position': 'Product Manager',
                'bio': 'Тестовый пользователь для демонстрации работы сервиса Code2Guide',
                'telegram': '@testuser',
                'github': 'testuser',
                'email_notifications': True,
                'telegram_notifications': False,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✅ Создан профиль пользователя'))

        # 2. Создаём подписку
        subscription, created = Subscription.objects.get_or_create(
            user=user,
            defaults={
                'plan': 'business',
                'projects_limit': 10,
                'generations_limit': 100,
                'word_available': True,
                'pdf_available': True,
                'remove_logo': True,
                'priority_support': True,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✅ Создана подписка Business'))

        # 3. Создаём проекты
        projects_data = [
            {
                'name': 'CRM-система для бизнеса',
                'description': 'Система управления взаимоотношениями с клиентами',
                'repo_url': 'https://github.com/company/crm-system',
                'branch': 'main',
                'instructions_count': 24,
            },
            {
                'name': 'Интернет-магазин',
                'description': 'Платформа для онлайн-торговли',
                'repo_url': 'https://github.com/company/ecommerce',
                'branch': 'develop',
                'instructions_count': 18,
            },
            {
                'name': 'Мобильное приложение',
                'description': 'Кроссплатформенное мобильное приложение',
                'repo_url': 'https://github.com/company/mobile-app',
                'branch': 'main',
                'instructions_count': 12,
            },
            {
                'name': 'API Gateway',
                'description': 'Единая точка входа для микросервисов',
                'repo_url': 'https://github.com/company/api-gateway',
                'branch': 'master',
                'instructions_count': 8,
            },
            {
                'name': 'Административная панель',
                'description': 'Панель управления для администраторов',
                'repo_url': 'https://github.com/company/admin-panel',
                'branch': 'main',
                'instructions_count': 15,
            },
        ]

        created_projects = []
        for project_data in projects_data:
            project, created = Project.objects.get_or_create(
                name=project_data['name'],
                user=user,
                defaults=project_data
            )
            created_projects.append(project)
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Создан проект: {project.name}'))

        # 4. Создаём генерации (историю)
        from datetime import datetime
        now = timezone.now()

        generations_data = [
            {
                'project': created_projects[0],
                'commit_hash': 'a1b2c3d4e5f6g7h8i9j0',
                'commit_message': 'feat: добавлен модуль аналитики',
                'components_count': 24,
                'status': 'completed',
            },
            {
                'project': created_projects[0],
                'commit_hash': 'b2c3d4e5f6g7h8i9j0k1',
                'commit_message': 'fix: исправлены ошибки валидации',
                'components_count': 3,
                'status': 'completed',
            },
            {
                'project': created_projects[1],
                'commit_hash': 'c3d4e5f6g7h8i9j0k1l2',
                'commit_message': 'refactor: оптимизация компонентов',
                'components_count': 12,
                'status': 'completed',
            },
            {
                'project': created_projects[1],
                'commit_hash': 'd4e5f6g7h8i9j0k1l2m3',
                'commit_message': 'feat: добавлена корзина товаров',
                'components_count': 8,
                'status': 'completed',
            },
            {
                'project': created_projects[2],
                'commit_hash': 'e5f6g7h8i9j0k1l2m3n4',
                'commit_message': 'style: обновлены стили компонентов',
                'components_count': 6,
                'status': 'in_progress',
            },
            {
                'project': created_projects[2],
                'commit_hash': 'f6g7h8i9j0k1l2m3n4o5',
                'commit_message': 'fix: исправлена навигация',
                'components_count': 4,
                'status': 'failed',
                'error_message': 'Ошибка при клонировании репозитория. Проверьте права доступа.'
            },
            {
                'project': created_projects[3],
                'commit_hash': 'g7h8i9j0k1l2m3n4o5p6',
                'commit_message': 'docs: обновлена документация API',
                'components_count': 9,
                'status': 'completed',
            },
            {
                'project': created_projects[4],
                'commit_hash': 'h8i9j0k1l2m3n4o5p6q7',
                'commit_message': 'feat: добавлена система уведомлений',
                'components_count': 5,
                'status': 'pending',
            },
        ]

        for gen_data in generations_data:
            generation, created = Generation.objects.get_or_create(
                commit_hash=gen_data['commit_hash'],
                project=gen_data['project'],
                defaults={
                    'user': user,
                    'commit_message': gen_data['commit_message'],
                    'components_count': gen_data['components_count'],
                    'status': gen_data['status'],
                    'error_message': gen_data.get('error_message', ''),
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Создана генерация: {generation.commit_hash}'))

        self.stdout.write(self.style.SUCCESS('\n🎉 Генерация моковых данных завершена!'))
        self.stdout.write('\n📋 Для входа в систему:')
        self.stdout.write(f'   Логин: testuser')
        self.stdout.write(f'   Пароль: test123')