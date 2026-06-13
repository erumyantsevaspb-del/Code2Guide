from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class Project(models.Model):
    """
    Модель проекта пользователя
    """
    name = models.CharField(
        max_length=200,
        verbose_name="Название проекта"
    )

    created_at = models.DateField(
        default=timezone.now,
        verbose_name="Дата создания"
    )

    instructions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество инструкций"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )

    # Связь с пользователем
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='projects',
        verbose_name="Пользователь",
        null=True,
        blank=True
    )

    # URL репозитория
    repo_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL репозитория"
    )

    # React архив проекта
    react_archive = models.FileField(
        upload_to='react_projects/',
        null=True,
        blank=True,
        verbose_name="React архив"
    )

    # Ветка для мониторинга
    branch = models.CharField(
        max_length=100,
        default='main',
        verbose_name="Ветка"
    )

    # Логотип проекта
    logo = models.ImageField(
        upload_to='project_logos/',
        null=True,
        blank=True,
        verbose_name="Логотип"
    )

    created_datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_formats(self):
        return ['Word', 'PDF']


class Generation(models.Model):
    """
    Модель генерации (история генераций)
    """
    STATUS_CHOICES = [
        ('pending', 'В очереди'),
        ('processing', 'В процессе'),
        ('completed', 'Завершено'),
        ('failed', 'Ошибка'),
    ]

    project = models.ForeignKey(
        'core.Project',
        on_delete=models.CASCADE,
        related_name='generations',
        verbose_name="Проект",
        null=True,
        blank=True
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='generations',
        verbose_name="Пользователь",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время"
    )

    commit_hash = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="Хеш коммита"
    )

    commit_message = models.TextField(
        blank=True,
        verbose_name="Сообщение коммита"
    )

    components_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Компоненты"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Статус"
    )

    error_message = models.TextField(
        blank=True,
        verbose_name="Сообщение об ошибке"
    )

    word_file = models.FileField(
        upload_to='generations/word/',
        null=True,
        blank=True,
        verbose_name="Word файл"
    )

    pdf_file = models.FileField(
        upload_to='generations/pdf/',
        null=True,
        blank=True,
        verbose_name="PDF файл"
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата завершения"
    )

    class Meta:
        verbose_name = "Генерация"
        verbose_name_plural = "Генерации"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.commit_hash} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"

    def get_status_display_ru(self):
        status_map = {
            'pending': 'В очереди',
            'processing': 'В процессе',
            'completed': 'Завершено',
            'failed': 'Ошибка',
        }
        return status_map.get(self.status, self.status)


class Profile(models.Model):
    """
    Расширенный профиль пользователя
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name="Пользователь"
    )

    # Контактная информация
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Телефон"
    )

    company = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Компания"
    )

    position = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Должность"
    )

    bio = models.TextField(
        blank=True,
        verbose_name="О себе"
    )

    # Социальные сети и интеграции
    telegram = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Telegram username"
    )

    github = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="GitHub username"
    )

    # Аватар
    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        verbose_name="Аватар"
    )

    # Настройки уведомлений
    email_notifications = models.BooleanField(
        default=True,
        verbose_name="Email уведомления"
    )

    telegram_notifications = models.BooleanField(
        default=False,
        verbose_name="Telegram уведомления"
    )

    # Временная зона
    timezone = models.CharField(
        max_length=50,
        default='Europe/Moscow',
        verbose_name="Часовой пояс"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self):
        return f"Профиль {self.user.username}"

    def get_full_name(self):
        """Возвращает полное имя пользователя"""
        if self.user.first_name or self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}".strip()
        return self.user.username


# Сигнал для автоматического создания профиля при регистрации пользователя
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Создаёт профиль автоматически при создании пользователя"""
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Сохраняет профиль при сохранении пользователя"""
    if hasattr(instance, 'profile'):
        instance.profile.save()


class Subscription(models.Model):
    """
    Модель подписки/тарифа пользователя
    """
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('starter', 'Starter'),
        ('business', 'Business'),
        ('enterprise', 'Enterprise'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='subscription',
        verbose_name="Пользователь"
    )

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default='free',
        verbose_name="Тариф"
    )

    projects_limit = models.PositiveIntegerField(
        default=1,
        verbose_name="Лимит проектов"
    )

    generations_limit = models.PositiveIntegerField(
        default=5,
        verbose_name="Лимит генераций в месяц"
    )

    word_available = models.BooleanField(
        default=False,
        verbose_name="Доступен Word"
    )

    pdf_available = models.BooleanField(
        default=True,
        verbose_name="Доступен PDF"
    )

    remove_logo = models.BooleanField(
        default=False,
        verbose_name="Убрать логотип сервиса"
    )

    priority_support = models.BooleanField(
        default=False,
        verbose_name="Приоритетная поддержка"
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата начала"
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата окончания"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()}"