import subprocess
from pathlib import Path
import tempfile
import shutil


def clone_repository(repo_url, branch='main'):
    """
    Клонирует репозиторий во временную папку.

    Возвращает путь к клонированному проекту.
    """

    temp_dir = tempfile.mkdtemp()

    try:
        subprocess.run(
            [
                'git',
                'clone',
                '--branch',
                branch,
                '--single-branch',
                repo_url,
                temp_dir
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return temp_dir

    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise