"""
Версия алгоритма и вспомогательные функции для фиксации параметров эксперимента.
Не содержит логики генерации — только идентификаторы и метаданные.
"""
import subprocess
from pathlib import Path

ALGORITHM_VERSION = 'V0'


def get_code_version() -> str:
    """Возвращает git commit hash текущей версии Code2Guide. Пустая строка если недоступен."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ''


def get_experiment_meta() -> dict:
    """Возвращает словарь с параметрами текущего эксперимента для сохранения в Generation."""
    return {
        'algorithm_version': ALGORITHM_VERSION,
        'code_version': get_code_version(),
    }
