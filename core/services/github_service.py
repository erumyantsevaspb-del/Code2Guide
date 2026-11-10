import subprocess
import os
from pathlib import Path
import tempfile
import shutil

_CLONE_TIMEOUT = 120  # секунды


def clone_repository(repo_url, branch='main'):
    """
    Клонирует репозиторий во временную папку.

    Возвращает путь к клонированному проекту.
    """

    temp_dir = tempfile.mkdtemp()

    try:
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'  # не блокируем HTTP-запрос интерактивным вводом

        subprocess.run(
            [
                'git',
                'clone',
                '--branch',
                branch,
                '--single-branch',
                '--depth', '1',
                repo_url,
                temp_dir,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_CLONE_TIMEOUT,
            env=env,
        )

        return temp_dir

    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise