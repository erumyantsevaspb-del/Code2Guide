from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


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

    # Связь с пользователем (опционально)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='projects',
        verbose_name="Пользователь",
        null=True,
        blank=True
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
        ('completed', 'Завершено'),
        ('in_progress', 'В процессе'),
        ('failed', 'Ошибка'),
    ]

    # Используем строковую ссылку на Project, чтобы избежать NameError
    project = models.ForeignKey(
        'core.Project',  # ← строковая ссылка вместо прямого имени
        on_delete=models.CASCADE,
        related_name='generations',
        verbose_name="Проект",
        null=True,
        blank=True
    )

    # Дата и время генерации
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время"
    )

    # Коммит (описание изменений)
    commit = models.CharField(
        max_length=255,
        verbose_name="Коммит",
        help_text="Описание изменений"
    )

    # Количество компонентов
    components_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Компоненты"
    )

    # Статус генерации
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='completed',
        verbose_name="Статус"
    )

    # Дополнительное описание
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )

    class Meta:
        verbose_name = "Генерация"
        verbose_name_plural = "Генерации"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.commit} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"

    def get_status_display_ru(self):
        """Возвращает статус на русском"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)