"""
Тесты классификации качества скриншотов: _classify_screenshot, _has_dynamic_segments,
и применение результатов в _take_screenshots_background.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.screenshot_service import _classify_screenshot, _has_dynamic_segments


# ---------------------------------------------------------------------------
# _has_dynamic_segments
# ---------------------------------------------------------------------------

def test_dynamic_segment_colon_id():
    assert _has_dynamic_segments('/users/:id') is True

def test_dynamic_segment_colon_user_id():
    assert _has_dynamic_segments('/profile/:userId/settings') is True

def test_static_path():
    assert _has_dynamic_segments('/research_list') is False

def test_root_path():
    assert _has_dynamic_segments('/') is False

def test_dynamic_segment_in_middle():
    assert _has_dynamic_segments('/projects/:projectId/tasks') is True


# ---------------------------------------------------------------------------
# _classify_screenshot: редирект
# ---------------------------------------------------------------------------

def _meta(title='', h1=''):
    return {'title': title, 'h1': h1}


def test_redirect_gives_unavailable():
    status, reason = _classify_screenshot(
        '/research_list', 'Список исследований',
        'http://127.0.0.1:3000/research_list',
        'http://127.0.0.1:3000/my_schedule',
        _meta('Мой график', 'Мой график'),
    )
    assert status == 'unavailable'
    assert 'редирект' in reason.lower() or 'redirect' in reason.lower() or '/my_schedule' in reason


def test_redirect_hash_router():
    """HashRouter: финальный URL содержит фрагмент другого пути → unavailable."""
    status, reason = _classify_screenshot(
        '/research_list', 'Список исследований',
        'http://127.0.0.1:3000/#/research_list',
        'http://127.0.0.1:3000/#/my_schedule',
        _meta('Мой график', 'Мой график'),
    )
    assert status == 'unavailable'


# ---------------------------------------------------------------------------
# _classify_screenshot: 404
# ---------------------------------------------------------------------------

def test_404_in_h1_gives_unavailable():
    status, reason = _classify_screenshot(
        '/admin/reports', 'Отчёты',
        'http://127.0.0.1:3000/admin/reports',
        'http://127.0.0.1:3000/admin/reports',
        _meta('Reports', 'Страница не найдена'),
    )
    assert status == 'unavailable'
    assert '404' in reason or 'не найдена' in reason.lower()


def test_not_found_english_gives_unavailable():
    status, reason = _classify_screenshot(
        '/settings', 'Настройки',
        'http://127.0.0.1:3000/settings',
        'http://127.0.0.1:3000/settings',
        _meta('Page not found', 'Page not found'),
    )
    assert status == 'unavailable'


def test_404_digit_in_title_gives_unavailable():
    status, reason = _classify_screenshot(
        '/old-page', 'Старая страница',
        'http://127.0.0.1:3000/old-page',
        'http://127.0.0.1:3000/old-page',
        _meta('404 | My App', ''),
    )
    assert status == 'unavailable'


# ---------------------------------------------------------------------------
# _classify_screenshot: динамический маршрут
# ---------------------------------------------------------------------------

def test_dynamic_route_gives_unavailable():
    status, reason = _classify_screenshot(
        '/patients/:id', 'Карточка пациента',
        'http://127.0.0.1:3000/patients/:id',
        'http://127.0.0.1:3000/patients/:id',
        _meta('', ''),
    )
    assert status == 'unavailable'
    assert ':id' in reason or 'динамическ' in reason.lower()


# ---------------------------------------------------------------------------
# _classify_screenshot: ok
# ---------------------------------------------------------------------------

def test_matching_url_and_title_gives_ok():
    status, reason = _classify_screenshot(
        '/research_list', 'Список исследований',
        'http://127.0.0.1:3000/research_list',
        'http://127.0.0.1:3000/research_list',
        _meta('Список исследований', 'Список исследований'),
    )
    assert status == 'ok'
    assert reason == ''


def test_ok_when_no_h1():
    """Если h1 пуст — нет оснований для needs_review."""
    status, reason = _classify_screenshot(
        '/dashboard', 'Дашборд',
        'http://127.0.0.1:3000/dashboard',
        'http://127.0.0.1:3000/dashboard',
        _meta('Dashboard', ''),
    )
    assert status == 'ok'


# ---------------------------------------------------------------------------
# _classify_screenshot: needs_review
# ---------------------------------------------------------------------------

def test_url_match_but_wrong_title_gives_needs_review():
    """URL совпал, но h1 содержит совсем другое — needs_review."""
    status, reason = _classify_screenshot(
        '/research_list', 'Список исследований',
        'http://127.0.0.1:3000/research_list',
        'http://127.0.0.1:3000/research_list',
        _meta('My Schedule', 'Мой график'),
    )
    assert status == 'needs_review'
    assert 'Мой график' in reason or 'Список исследований' in reason


def test_partial_token_match_is_ok():
    """Если хотя бы один длинный токен точно совпадает — ok, не needs_review."""
    status, reason = _classify_screenshot(
        '/research_list', 'Список исследований',
        'http://127.0.0.1:3000/research_list',
        'http://127.0.0.1:3000/research_list',
        _meta('Список исследований', 'Список исследований'),
    )
    # «список» и «исследований» входят в оба → ok
    assert status == 'ok'


# ---------------------------------------------------------------------------
# Применение в _take_screenshots_background
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_screenshot_unavailable_not_attached_to_instruction(tmp_path):
    """
    Если скриншот помечен unavailable (редирект), в instruction_data
    поле screenshot должно быть None, а screenshot_status — 'unavailable'.
    """
    from core.models import Project, Generation
    from core.views import _take_screenshots_background

    project = Project.objects.create(name='test_classify')
    gen = Generation.objects.create(
        project=project,
        status='processing',
        instruction_data=[
            {'name': 'Список исследований', 'path': '/research_list',
             'instructions': [], 'screenshot': None},
        ],
    )

    # Имитируем: take_route_screenshots вернул unavailable для /research_list
    mock_screenshots = {
        '/research_list': {
            'file': None,
            'status': 'unavailable',
            'reason': 'Редирект: /research_list → /my_schedule',
            'final_url': 'http://127.0.0.1:3000/my_schedule',
            'title': 'Мой график',
            'h1': 'Мой график',
        }
    }

    with patch('core.services.screenshot_service.take_route_screenshots', return_value=mock_screenshots), \
         patch('core.services.screenshot_service._install_dependencies'), \
         patch('core.views.take_route_screenshots', return_value=mock_screenshots):
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(tmp_path),
            cleanup_path=str(tmp_path),
            routes=[{'path': '/research_list', 'name': 'Список исследований'}],
            project_id=project.id,
        )

    gen.refresh_from_db()
    item = gen.instruction_data[0]
    assert item['screenshot'] is None, "screenshot должен быть None для unavailable"
    assert item['screenshot_status'] == 'unavailable'
    assert 'редирект' in item['screenshot_reason'].lower() or '/my_schedule' in item['screenshot_reason']

    Project.objects.filter(pk=project.pk).delete()


@pytest.mark.django_db
def test_screenshot_needs_review_file_is_kept(tmp_path):
    """
    Если скриншот помечен needs_review, файл остаётся, но статус — needs_review.
    """
    from core.models import Project, Generation
    from core.views import _take_screenshots_background

    project = Project.objects.create(name='test_needs_review')
    gen = Generation.objects.create(
        project=project,
        status='processing',
        instruction_data=[
            {'name': 'Список исследований', 'path': '/research_list',
             'instructions': [], 'screenshot': None},
        ],
    )

    mock_screenshots = {
        '/research_list': {
            'file': 'screenshots/1/research_list.png',
            'status': 'needs_review',
            'reason': 'Заголовок страницы «Мой график» не совпадает с разделом «Список исследований»',
            'final_url': 'http://127.0.0.1:3000/research_list',
            'title': 'My Schedule',
            'h1': 'Мой график',
        }
    }

    with patch('core.views.take_route_screenshots', return_value=mock_screenshots):
        _take_screenshots_background(
            generation_id=gen.id,
            source_path=str(tmp_path),
            cleanup_path=str(tmp_path),
            routes=[{'path': '/research_list', 'name': 'Список исследований'}],
            project_id=project.id,
        )

    gen.refresh_from_db()
    item = gen.instruction_data[0]
    assert item['screenshot'] == 'screenshots/1/research_list.png', "файл нужно сохранить"
    assert item['screenshot_status'] == 'needs_review'

    Project.objects.filter(pk=project.pk).delete()
