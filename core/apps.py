import logging
import os
import sys
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Пропускаем при запуске pytest — тестовая БД ещё не создана в момент ready().
        if 'pytest' in os.environ.get('DJANGO_SETTINGS_MODULE', '') or _is_pytest():
            return

        # Пропускаем для management-команд: они управляют БД сами.
        # repair_stuck_generations --dry-run особенно важен: startup не должен его опережать.
        if _is_management_command():
            return

        run_main = os.environ.get('RUN_MAIN')
        # manage.py runserver запускает два процесса (авторелоадер):
        #   родительский: RUN_MAIN не установлен → пропускаем
        #   дочерний:     RUN_MAIN=true          → запускаем
        # --noreload: один процесс, RUN_MAIN не установлен → запускаем.
        # Production (gunicorn/uWSGI): RUN_MAIN не установлен, команда не runserver → запускаем.
        argv = sys.argv
        is_runserver = len(argv) >= 2 and argv[1] == 'runserver'
        is_noreload = '--noreload' in argv
        if is_runserver and run_main != 'true' and not is_noreload:
            return
        # Родительский процесс авторелоадера для нестандартных команд — не бывает,
        # но на всякий случай: RUN_MAIN=false явно → пропускаем.
        if run_main == 'false':
            return

        try:
            _repair_stuck_on_startup()
        except Exception:
            # БД может быть не готова (первый запуск до migrate) — логируем, не падаем.
            logger.warning('repair_stuck_on_startup: не удалось выполнить очистку при старте', exc_info=True)


def _is_pytest() -> bool:
    """Возвращает True, если процесс запущен под pytest."""
    return 'pytest' in sys.modules or os.environ.get('PYTEST_CURRENT_TEST') is not None


# Management-команды, при которых startup-repair не нужен.
# repair_stuck_generations — особо важно: dry-run должен оставаться dry-run.
_SKIP_COMMANDS = frozenset({
    'repair_stuck_generations',
    'migrate',
    'makemigrations',
    'check',
    'shell',
    'test',
    'dbshell',
    'showmigrations',
    'sqlmigrate',
    'createsuperuser',
    'collectstatic',
    'dumpdata',
    'loaddata',
})


def _is_management_command() -> bool:
    """Возвращает True, если manage.py запущен с командой из SKIP-списка."""
    argv = sys.argv
    # sys.argv = ['manage.py', 'command_name', ...]
    if len(argv) >= 2 and argv[1] in _SKIP_COMMANDS:
        return True
    return False


def _repair_stuck_on_startup():
    """Переводит старые processing-генерации в failed при запуске Django."""
    from django.utils import timezone
    from datetime import timedelta
    from .constants import SCREENSHOT_ZOMBIE_TIMEOUT

    from .models import Generation

    cutoff = timezone.now() - timedelta(seconds=SCREENSHOT_ZOMBIE_TIMEOUT)
    stuck = Generation.objects.filter(status='processing', created_at__lt=cutoff)
    count = stuck.count()
    if not count:
        return

    now = timezone.now()
    updated = 0
    for gen in stuck:
        elapsed = int((now - gen.created_at).total_seconds())
        gen.status = 'failed'
        gen.error_message = (
            f'Зависание при запуске: генерация не завершилась за {elapsed // 60} мин. '
            f'Фоновый поток был прерван при перезапуске сервера. '
            f'Запустите генерацию повторно.'
        )
        gen.completed_at = now
        gen.duration_seconds = elapsed
        gen.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
        updated += 1

    print(f'[startup] repair_stuck_generations: исправлено {updated} зависших генераций.')
