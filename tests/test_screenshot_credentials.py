"""
Тесты классификации скриншотов в take_screenshots_with_credentials:
редирект, 404, динамический маршрут, несовпадение заголовка.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()


def _make_cred_page(final_url='http://app.example.com/', title='', h1_visible=False, h1_text=''):
    """Создаёт мок page для take_screenshots_with_credentials."""
    page = MagicMock()
    page.goto.return_value = None
    page.title.return_value = title

    # page.url — свойство, возвращает final_url
    type(page).url = PropertyMock(return_value=final_url)

    # h1 locator
    h1_mock = MagicMock()
    h1_mock.is_visible.return_value = h1_visible
    h1_mock.inner_text.return_value = h1_text
    page.locator.return_value.first = h1_mock

    # input[type="password"] — не видим (не login-форма)
    pwd_mock = MagicMock()
    pwd_mock.is_visible.return_value = False
    page.locator.return_value.first = pwd_mock  # переопределим ниже где нужно

    return page


def _make_page_with_metas(final_url, title='', h1=''):
    """Мок page с правильным url, title(), locator() для h1."""
    page = MagicMock()
    page.goto.return_value = None
    page.title.return_value = title
    type(page).url = PropertyMock(return_value=final_url)

    def locator_side_effect(selector):
        mock_loc = MagicMock()
        if selector == 'h1':
            mock_first = MagicMock()
            mock_first.is_visible.return_value = bool(h1)
            mock_first.inner_text.return_value = h1
            mock_loc.first = mock_first
        else:
            # input[type="password"] etc. — не видим
            mock_first = MagicMock()
            mock_first.is_visible.return_value = False
            mock_loc.first = mock_first
        return mock_loc

    page.locator.side_effect = locator_side_effect
    return page


def _run_with_creds(routes, page, screenshot_creates_file=True):
    """Запускает take_screenshots_with_credentials с мок-браузером."""
    from core.services.screenshot_service import take_screenshots_with_credentials

    def fake_screenshot(path, **kwargs):
        if screenshot_creates_file:
            Path(path).touch()

    page.screenshot.side_effect = fake_screenshot

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = mock_p
    mock_sp.return_value.__exit__.return_value = False

    with patch('core.services.screenshot_service.sync_playwright', mock_sp), \
         patch('core.services.screenshot_service._do_login', return_value=True), \
         patch('core.services.screenshot_service.time.sleep'):
        return take_screenshots_with_credentials(
            'http://app.example.com', 'user', 'pass',
            routes, project_id=55,
        )


# ── Редирект → unavailable ────────────────────────────────────────────────────

def test_creds_redirect_gives_unavailable():
    """Финальный URL отличается от запрошенного → unavailable."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/my_schedule',
        title='Мой график', h1='Мой график',
    )
    result = _run_with_creds(
        [{'path': '/research_list', 'name': 'Список исследований'}],
        page,
    )
    assert '/research_list' in result
    item = result['/research_list']
    assert item['status'] == 'unavailable', f"Ожидался unavailable: {item}"
    assert item['file'] is None
    assert 'редирект' in item['reason'].lower() or '/my_schedule' in item['reason']


# ── 404 → unavailable ────────────────────────────────────────────────────────

def test_creds_404_title_gives_unavailable():
    """«404» в заголовке страницы → unavailable."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/old-page',
        title='404 | My App', h1='',
    )
    result = _run_with_creds(
        [{'path': '/old-page', 'name': 'Старая страница'}],
        page,
    )
    item = result['/old-page']
    assert item['status'] == 'unavailable', f"Ожидался unavailable: {item}"
    assert item['file'] is None


def test_creds_page_not_found_h1_gives_unavailable():
    """«Страница не найдена» в h1 → unavailable."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/settings',
        title='Настройки', h1='Страница не найдена',
    )
    result = _run_with_creds(
        [{'path': '/settings', 'name': 'Настройки'}],
        page,
    )
    item = result['/settings']
    assert item['status'] == 'unavailable', f"Ожидался unavailable: {item}"
    assert item['file'] is None


# ── Динамический маршрут → unavailable ───────────────────────────────────────

def test_creds_dynamic_route_gives_unavailable():
    """Маршрут с :id → unavailable без запроса к серверу."""
    page = _make_page_with_metas(final_url='http://app.example.com/patients/123')
    goto_called = []
    page.goto.side_effect = lambda *a, **kw: goto_called.append(a)

    result = _run_with_creds(
        [{'path': '/patients/:id', 'name': 'Карточка пациента'}],
        page,
    )
    item = result['/patients/:id']
    assert item['status'] == 'unavailable', f"Ожидался unavailable: {item}"
    assert item['file'] is None
    assert not goto_called, "goto не должен вызываться для динамических маршрутов"


# ── Несовпадение заголовка → needs_review ────────────────────────────────────

def test_creds_title_mismatch_gives_needs_review():
    """URL совпал, но h1 содержит другое название → needs_review, файл сохраняется."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/research_list',
        title='My Schedule', h1='Мой график',
    )
    result = _run_with_creds(
        [{'path': '/research_list', 'name': 'Список исследований'}],
        page,
    )
    item = result['/research_list']
    assert item['status'] == 'needs_review', f"Ожидался needs_review: {item}"
    assert item['file'] is not None, "Файл должен быть сохранён для needs_review"
    assert item['file'].endswith('.png')


# ── Успешный скриншот → ok ────────────────────────────────────────────────────

def test_creds_matching_page_gives_ok():
    """URL и заголовок совпадают → ok, файл сохраняется."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/research_list',
        title='Список исследований', h1='Список исследований',
    )
    result = _run_with_creds(
        [{'path': '/research_list', 'name': 'Список исследований'}],
        page,
    )
    item = result['/research_list']
    assert item['status'] == 'ok', f"Ожидался ok: {item}"
    assert item['file'] is not None
    assert item['file'].endswith('.png')


# ── Формат ответа единый ─────────────────────────────────────────────────────

def test_creds_result_has_required_keys():
    """Каждая запись содержит все обязательные ключи."""
    page = _make_page_with_metas(
        final_url='http://app.example.com/dashboard',
        title='Dashboard', h1='',
    )
    result = _run_with_creds(
        [{'path': '/dashboard', 'name': 'Dashboard'}],
        page,
    )
    item = result['/dashboard']
    for key in ('file', 'status', 'reason', 'final_url', 'title', 'h1'):
        assert key in item, f"Ключ '{key}' отсутствует: {item}"
