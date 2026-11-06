"""
Команда для восстановления зависших генераций.

Генерации, застрявшие в статусе 'processing' дольше заданного таймаута,
переводятся в 'failed' с понятным сообщением об ошибке.

Типичная причина: сервер был перезапущен, daemon-поток завершился,
но Generation.status не обновился.

Использование:
    python manage.py repair_stuck_generations
    python manage.py repair_stuck_generations --timeout 30
    python manage.py repair_stuck_generations --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from core.models import Generation
from core.constants import SCREENSHOT_ZOMBIE_TIMEOUT


class Command(BaseCommand):
    help = 'Переводит зависшие processing-генерации в failed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=SCREENSHOT_ZOMBIE_TIMEOUT // 60,
            metavar='MINUTES',
            help=f'Таймаут в минутах (по умолчанию: {SCREENSHOT_ZOMBIE_TIMEOUT // 60})',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет исправлено, без изменений в БД',
        )

    def handle(self, *args, **options):
        timeout_minutes = options['timeout']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(minutes=timeout_minutes)

        stuck = Generation.objects.filter(
            status='processing',
            created_at__lt=cutoff,
        ).order_by('created_at')

        count = stuck.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                f'Зависших генераций не найдено (таймаут: {timeout_minutes} мин).'
            ))
            return

        mode = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            f'{mode}Найдено {count} зависших генераций (старше {timeout_minutes} мин):'
        )

        now = timezone.now()
        fixed = 0
        for gen in stuck:
            elapsed = (now - gen.created_at).total_seconds()
            elapsed_min = int(elapsed // 60)
            self.stdout.write(
                f'  id={gen.id} project_id={gen.project_id} '
                f'создана {gen.created_at.strftime("%Y-%m-%d %H:%M")} '
                f'({elapsed_min} мин назад)'
            )
            if not dry_run:
                gen.status = 'failed'
                gen.error_message = (
                    f'Таймаут: генерация не завершилась за {elapsed_min} мин. '
                    f'Фоновый процесс завершился без обновления статуса '
                    f'(вероятно, сервер был перезапущен). '
                    f'Запустите генерацию повторно.'
                )
                gen.completed_at = now
                gen.duration_seconds = int(elapsed)
                gen.save(update_fields=[
                    'status', 'error_message', 'completed_at', 'duration_seconds'
                ])
                fixed += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY-RUN] Будет исправлено: {count}. Запустите без --dry-run для применения.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Исправлено: {fixed} из {count} генераций.'
            ))
