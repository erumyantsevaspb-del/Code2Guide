"""
Тесты NX-поддержки скриншотов: find_nx_serve_apps и логика выбора приложения.
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.screenshot_service import find_nx_serve_apps


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _make_nx_project(tmp_path: Path, apps: dict) -> Path:
    """
    Создаёт минимальную структуру NX monorepo в tmp_path.
    apps: {app_name: has_serve_target}
    Возвращает путь к корню проекта.
    """
    root = tmp_path / 'project'
    root.mkdir()

    # Корневой package.json с NX в dev-скрипте
    (root / 'package.json').write_text(json.dumps({
        'name': 'monorepo',
        'scripts': {'dev': 'npx nx run shell:serve --port=3000'},
    }), encoding='utf-8')

    apps_dir = root / 'apps'
    apps_dir.mkdir()

    for app_name, has_serve in apps.items():
        app_dir = apps_dir / app_name
        app_dir.mkdir()
        targets = {}
        if has_serve:
            targets['serve'] = {'executor': '@nrwl/vite:dev-server'}
        (app_dir / 'project.json').write_text(json.dumps({
            'name': app_name,
            'targets': targets,
        }), encoding='utf-8')

    return root


# ---------------------------------------------------------------------------
# Тесты find_nx_serve_apps
# ---------------------------------------------------------------------------

def test_find_nx_serve_apps_single(tmp_path):
    """Единственное приложение с serve → список из одного элемента."""
    root = _make_nx_project(tmp_path, {'shell': True, 'lib': False})
    result = find_nx_serve_apps(str(root))
    assert result == ['shell']


def test_find_nx_serve_apps_multiple(tmp_path):
    """Несколько приложений с serve → все возвращаются."""
    root = _make_nx_project(tmp_path, {'auth': True, 'shell': True, 'lib': False})
    result = find_nx_serve_apps(str(root))
    assert set(result) == {'auth', 'shell'}


def test_find_nx_serve_apps_none(tmp_path):
    """Нет приложений с serve → пустой список."""
    root = _make_nx_project(tmp_path, {'lib': False, 'utils': False})
    result = find_nx_serve_apps(str(root))
    assert result == []


def test_find_nx_serve_apps_no_apps_dir(tmp_path):
    """Нет папки apps/ → пустой список без исключений."""
    root = tmp_path / 'plain'
    root.mkdir()
    (root / 'package.json').write_text('{}', encoding='utf-8')
    result = find_nx_serve_apps(str(root))
    assert result == []


def test_find_nx_serve_apps_ignores_node_modules(tmp_path):
    """project.json внутри node_modules игнорируется."""
    root = _make_nx_project(tmp_path, {'shell': True})
    nm_dir = root / 'apps' / 'node_modules' / 'fake'
    nm_dir.mkdir(parents=True)
    (nm_dir / 'project.json').write_text(json.dumps({'name': 'fake', 'targets': {'serve': {}}}), encoding='utf-8')
    result = find_nx_serve_apps(str(root))
    assert 'fake' not in result
    assert result == ['shell']


def test_find_nx_serve_apps_real_p29(tmp_path):
    """Тест на реальном ZIP проекта №29 (react-pa-doctor-develop)."""
    import zipfile
    zip_path = Path('C:/Users/Lena/Code2Guide/media/react_projects/react-pa-doctor-develop.zip')
    if not zip_path.exists():
        pytest.skip("ZIP p29 не найден")

    extract_dir = tmp_path / 'p29'
    extract_dir.mkdir()
    with zipfile.ZipFile(str(zip_path)) as zf:
        # Распаковываем только project.json и package.json для скорости
        for name in zf.namelist():
            if name.endswith('project.json') or (name.endswith('package.json') and name.count('/') <= 1):
                dest = extract_dir / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))

    # Корень проекта — первый подкаталог
    subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    assert subdirs, "ZIP должен содержать подкаталог"
    project_root = subdirs[0]

    result = find_nx_serve_apps(str(project_root))
    assert result == ['shell'], f"p29 должен содержать ровно одно serve-приложение 'shell', получено: {result}"


# ---------------------------------------------------------------------------
# Тесты логики выбора NX-приложения в _take_screenshots_background
# (юнит: мокируем вызовы, не запускаем реальный сервер)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_nx_autoselect_single_app(tmp_path):
    """При одном serve-приложении и пустом nx_app_name → авто-запуск через take_nx_screenshots."""
    from core.models import Project, Generation
    from django.utils import timezone

    root = _make_nx_project(tmp_path, {'shell': True})

    project = Project.objects.create(name='test_nx_single')
    gen = Generation.objects.create(
        project=project, status='processing',
        instruction_data=[{'path': '/', 'name': 'home', 'instructions': []}],
    )

    with patch('core.services.screenshot_service.find_nx_serve_apps', return_value=['shell']), \
         patch('core.services.screenshot_service.take_nx_screenshots', return_value={'/': {'file': 'screenshots/1/index.png', 'status': 'ok', 'reason': ''}}) as mock_nx, \
         patch('core.views.take_route_screenshots') as mock_local:
        # Импортируем _take_screenshots_background после patch
        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(root),
            cleanup_path=str(root),
            routes=[{'path': '/', 'name': 'home'}],
            project_id=project.id,
            nx_app_name=None,
        )

    mock_nx.assert_called_once()
    mock_local.assert_not_called()
    gen.refresh_from_db()
    assert gen.status == 'completed'

    Project.objects.filter(pk=project.pk).delete()


@pytest.mark.django_db
def test_nx_multiple_apps_no_choice(tmp_path):
    """При нескольких serve-приложениях и пустом nx_app_name → completed_without_screenshots."""
    from core.models import Project, Generation

    root = _make_nx_project(tmp_path, {'shell': True, 'auth': True})

    project = Project.objects.create(name='test_nx_multi')
    gen = Generation.objects.create(project=project, status='processing')

    with patch('core.services.screenshot_service.find_nx_serve_apps', return_value=['auth', 'shell']), \
         patch('core.services.screenshot_service.take_nx_screenshots') as mock_nx:
        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(root),
            cleanup_path=str(root),
            routes=[{'path': '/', 'name': 'home'}],
            project_id=project.id,
            nx_app_name=None,
        )

    mock_nx.assert_not_called()
    gen.refresh_from_db()
    assert gen.status == 'completed_without_screenshots'
    assert 'выберите' in gen.error_message.lower() or 'доступные' in gen.error_message.lower()

    Project.objects.filter(pk=project.pk).delete()


@pytest.mark.django_db
def test_nx_detected_apps_saved_to_project(tmp_path):
    """После генерации nx_detected_apps сохраняется в Project."""
    from core.models import Project, Generation

    root = _make_nx_project(tmp_path, {'shell': True, 'auth': True})

    project = Project.objects.create(name='test_nx_save_detected')
    gen = Generation.objects.create(project=project, status='processing')

    with patch('core.services.screenshot_service.find_nx_serve_apps', return_value=['auth', 'shell']), \
         patch('core.services.screenshot_service.take_nx_screenshots') as mock_nx:
        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(root),
            cleanup_path=str(root),
            routes=[{'path': '/', 'name': 'home'}],
            project_id=project.id,
            nx_app_name=None,
        )

    project.refresh_from_db()
    assert set(project.nx_detected_apps) == {'auth', 'shell'}, \
        f"nx_detected_apps должны быть сохранены, получено: {project.nx_detected_apps}"

    Project.objects.filter(pk=project.pk).delete()


@pytest.mark.django_db
def test_nx_explicit_app_used(tmp_path):
    """Явно указанный nx_app_name используется для take_nx_screenshots."""
    from core.models import Project, Generation

    root = _make_nx_project(tmp_path, {'shell': True, 'auth': True})

    project = Project.objects.create(name='test_nx_explicit')
    gen = Generation.objects.create(
        project=project, status='processing',
        instruction_data=[{'path': '/', 'name': 'home', 'instructions': []}],
    )

    with patch('core.services.screenshot_service.find_nx_serve_apps', return_value=['auth', 'shell']), \
         patch('core.services.screenshot_service.take_nx_screenshots', return_value={'/': {'file': 'screenshots/1/index.png', 'status': 'ok', 'reason': ''}}) as mock_nx:
        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(root),
            cleanup_path=str(root),
            routes=[{'path': '/', 'name': 'home'}],
            project_id=project.id,
            nx_app_name='shell',
        )

    mock_nx.assert_called_once()
    call_args = mock_nx.call_args
    assert call_args[0][1] == 'shell'
    gen.refresh_from_db()
    assert gen.status == 'completed'

    Project.objects.filter(pk=project.pk).delete()


@pytest.mark.django_db
def test_nx_wrong_app_name(tmp_path):
    """Указано несуществующее NX-приложение → completed_without_screenshots с понятной причиной."""
    from core.models import Project, Generation

    root = _make_nx_project(tmp_path, {'shell': True})

    project = Project.objects.create(name='test_nx_wrong')
    gen = Generation.objects.create(project=project, status='processing')

    with patch('core.services.screenshot_service.find_nx_serve_apps', return_value=['shell']), \
         patch('core.services.screenshot_service.take_nx_screenshots') as mock_nx:
        from core.views import _take_screenshots_background
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(root),
            cleanup_path=str(root),
            routes=[{'path': '/', 'name': 'home'}],
            project_id=project.id,
            nx_app_name='nonexistent',
        )

    mock_nx.assert_not_called()
    gen.refresh_from_db()
    assert gen.status == 'completed_without_screenshots'
    assert 'nonexistent' in gen.error_message

    Project.objects.filter(pk=project.pk).delete()
