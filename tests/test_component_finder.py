"""
Тесты find_component_by_name и W6-исправления parse_component_pages_fallback.

Покрывает:
- Поиск компонента по имени в src/pages/ (прямой файл)
- Поиск компонента как index.tsx в директории
- Поиск в src/views/ (субдиректории)
- Компонент не найден → None
- W6: fallback находит компоненты во вложенных директориях
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.jsx_parser import find_component_by_name
from core.services.react_parser import parse_component_pages_fallback


def _make_project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── find_component_by_name ────────────────────────────────────────────

def test_find_by_name_direct_file():
    """Dashboard.tsx в src/pages/ — найден напрямую."""
    src = _make_project({'src/pages/Dashboard.tsx': 'export default function Dashboard() { return <h1>Dash</h1>; }'})
    result = find_component_by_name(src, 'Dashboard')
    assert result is not None, "Должен найти Dashboard.tsx"
    assert 'Dashboard' in result.name
    print(f"  PASS test_find_by_name_direct_file: {result}")


def test_find_by_name_index_file():
    """Settings/index.tsx — найден через index."""
    src = _make_project({'src/views/Settings/index.tsx': 'export default function Settings() {}'})
    result = find_component_by_name(src, 'Settings')
    assert result is not None, "Должен найти Settings/index.tsx"
    assert result.name == 'index.tsx'
    assert result.parent.name == 'Settings'
    print(f"  PASS test_find_by_name_index_file: {result}")


def test_find_by_name_nested_dir():
    """UsersPage.tsx в src/views/users/ — найден рекурсивно."""
    src = _make_project({'src/views/users/UsersPage.tsx': 'export default function UsersPage() {}'})
    result = find_component_by_name(src, 'UsersPage')
    assert result is not None, "Должен найти UsersPage.tsx в субдиректории"
    print(f"  PASS test_find_by_name_nested_dir: {result}")


def test_find_by_name_case_insensitive():
    """dashboard.tsx (lowercase) ищем как 'Dashboard' — найден без учёта регистра."""
    src = _make_project({'src/pages/dashboard.tsx': 'export default function Dashboard() {}'})
    result = find_component_by_name(src, 'Dashboard')
    assert result is not None, "Должен найти dashboard.tsx case-insensitively"
    print(f"  PASS test_find_by_name_case_insensitive: {result}")


def test_find_by_name_not_found():
    """Компонента нет → None."""
    src = _make_project({'src/pages/Home.tsx': 'export default function Home() {}'})
    result = find_component_by_name(src, 'NonExistent')
    assert result is None, f"Должен вернуть None, получили {result}"
    print("  PASS test_find_by_name_not_found")


def test_find_by_name_empty_name():
    """Пустое имя → None (не падает)."""
    src = _make_project({'src/pages/Home.tsx': 'export default function Home() {}'})
    result = find_component_by_name(src, '')
    assert result is None, f"Должен вернуть None для пустого имени, получили {result}"
    print("  PASS test_find_by_name_empty_name")


def test_find_by_name_skips_node_modules():
    """node_modules не сканируется."""
    src = _make_project({
        'node_modules/Dashboard/index.tsx': 'export default function Dashboard() {}',
        'src/Other.tsx': 'export default function Other() {}',
    })
    result = find_component_by_name(src, 'Dashboard')
    assert result is None, f"node_modules не должен сканироваться, получили {result}"
    print("  PASS test_find_by_name_skips_node_modules")


# ── .page / .screen суффиксы (p22, ЛК) ───────────────────────────────

def test_find_page_suffix_tsx():
    """appoints.page.tsx найден по ключу 'appoints' (p22-паттерн)."""
    src = _make_project({'apps/crm/src/pages/appoints/ui/appoints.page.tsx': 'export default function AppointsPage() {}'})
    result = find_component_by_name(src, 'appoints')
    assert result is not None, "Должен найти appoints.page.tsx для ключа 'appoints'"
    assert result.name == 'appoints.page.tsx'
    print(f"  PASS test_find_page_suffix_tsx: {result}")


def test_find_screen_suffix():
    """Home.screen.tsx найден по ключу 'Home'."""
    src = _make_project({'src/pages/Home.screen.tsx': 'export default function HomeScreen() {}'})
    result = find_component_by_name(src, 'Home')
    assert result is not None, "Должен найти Home.screen.tsx для ключа 'Home'"
    assert result.name == 'Home.screen.tsx'
    print(f"  PASS test_find_screen_suffix: {result}")


def test_find_dot_normalized():
    """duty.schedule.tsx найден по ключу 'duty_schedule' (нормализация точек)."""
    src = _make_project({'apps/crm/src/pages/duty.schedule.tsx': 'export default function DutySchedule() {}'})
    result = find_component_by_name(src, 'duty_schedule')
    assert result is not None, "Должен найти duty.schedule.tsx для ключа 'duty_schedule'"
    assert result.name == 'duty.schedule.tsx'
    print(f"  PASS test_find_dot_normalized: {result}")


def test_find_page_suffix_with_dot_key():
    """salary.history.page.tsx найден по ключу 'salary_history' (суффикс + нормализация)."""
    src = _make_project({'apps/crm/src/pages/salary/salary.history.page.tsx': 'export default function SalaryHistory() {}'})
    result = find_component_by_name(src, 'salary_history')
    assert result is not None, "Должен найти salary.history.page.tsx для ключа 'salary_history'"
    assert result.name == 'salary.history.page.tsx'
    print(f"  PASS test_find_page_suffix_with_dot_key: {result}")


def test_find_hyphen_normalized():
    """patient-record-create.page.tsx найден по ключу 'patient_record_create' (дефисы)."""
    src = _make_project({'apps/main/src/pages/patient-record-create.page.tsx': 'export default function PatientRecordCreate() {}'})
    result = find_component_by_name(src, 'patient_record_create')
    assert result is not None, "Должен найти patient-record-create.page.tsx для ключа 'patient_record_create'"
    assert result.name == 'patient-record-create.page.tsx'
    print(f"  PASS test_find_hyphen_normalized: {result}")


def test_find_lab_page_lk():
    """lab.page.tsx в NX-монорепо найден по ключу 'lab' (ЛК-паттерн)."""
    src = _make_project({'apps/lab/src/pages/lab/ui/lab.page.tsx': 'export default function LabPage() {}'})
    result = find_component_by_name(src, 'lab')
    assert result is not None, "Должен найти lab.page.tsx для ключа 'lab'"
    assert result.name == 'lab.page.tsx'
    print(f"  PASS test_find_lab_page_lk: {result}")


def test_find_plural_suffix_months():
    """statements.revenues.month.page.tsx найден по ключу 'statements_revenues_months' (±s)."""
    src = _make_project({'pages/statements/revenues/statements.revenues.month.page.tsx': 'export default function Rev() {}'})
    result = find_component_by_name(src, 'statements_revenues_months')
    assert result is not None, "Должен найти statements.revenues.month.page.tsx для ключа 'statements_revenues_months'"
    assert result.name == 'statements.revenues.month.page.tsx'
    print(f"  PASS test_find_plural_suffix_months: {result}")


def test_find_singular_to_plural():
    """manage.centers.page.tsx найден по ключу 'manage_center' (center→centers)."""
    src = _make_project({'pages/manage.centers.page.tsx': 'export default function ManageCenters() {}'})
    result = find_component_by_name(src, 'manage_center')
    assert result is not None, "Должен найти manage.centers.page.tsx для ключа 'manage_center'"
    assert result.name == 'manage.centers.page.tsx'
    print(f"  PASS test_find_singular_to_plural: {result}")


def test_no_false_positive_partial_match():
    """appoints_deals.page.tsx НЕ найден по ключу 'appoints' (без частичного совпадения)."""
    src = _make_project({'src/pages/appoints_deals.page.tsx': 'export default function AppointsDealPage() {}'})
    result = find_component_by_name(src, 'appoints')
    assert result is None, f"Не должен находить appoints_deals по ключу 'appoints', получили {result}"
    print("  PASS test_no_false_positive_partial_match")


# ── W6: fallback с рекурсией (rglob) ─────────────────────────────────

def test_w6_fallback_finds_subdir_components():
    """W6 fix: parse_component_pages_fallback находит файлы в субдиректориях src/views/."""
    src = _make_project({
        'src/views/dashboard/DashboardPage.tsx': 'export default function DashboardPage() {}',
        'src/views/settings/SettingsPage.tsx': 'export default function SettingsPage() {}',
    })
    routes = parse_component_pages_fallback(src)
    paths = [r['path'] for r in routes]
    assert '/dashboard' in paths, f"W6 FAIL: нет '/dashboard' в {paths}"
    assert '/settings' in paths, f"W6 FAIL: нет '/settings' в {paths}"
    print(f"  PASS test_w6_fallback_finds_subdir_components: {paths}")


def test_w6_fallback_first_level_still_works():
    """Регрессия W6: первый уровень src/pages/ по-прежнему работает."""
    src = _make_project({
        'src/pages/Users.tsx': 'export default function Users() {}',
        'src/pages/Orders.tsx': 'export default function Orders() {}',
    })
    routes = parse_component_pages_fallback(src)
    paths = [r['path'] for r in routes]
    assert '/users' in paths, f"Регрессия: нет '/users' в {paths}"
    assert '/orders' in paths, f"Регрессия: нет '/orders' в {paths}"
    print(f"  PASS test_w6_fallback_first_level_still_works: {paths}")


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import shutil
    tests = [
        test_find_by_name_direct_file,
        test_find_by_name_index_file,
        test_find_by_name_nested_dir,
        test_find_by_name_case_insensitive,
        test_find_by_name_not_found,
        test_find_by_name_empty_name,
        test_find_by_name_skips_node_modules,
        test_find_page_suffix_tsx,
        test_find_screen_suffix,
        test_find_dot_normalized,
        test_find_page_suffix_with_dot_key,
        test_find_hyphen_normalized,
        test_find_lab_page_lk,
        test_find_plural_suffix_months,
        test_find_singular_to_plural,
        test_no_false_positive_partial_match,
        test_w6_fallback_finds_subdir_components,
        test_w6_fallback_first_level_still_works,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("find_component_by_name + W6 fallback — тесты")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}\n")

    import sys
    sys.exit(0 if failed == 0 else 1)
