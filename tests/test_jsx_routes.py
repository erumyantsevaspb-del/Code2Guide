"""
Тесты parse_jsx_routes() для React Router v6 JSX-формата.

Покрывают:
- Плоские маршруты (burakorkmez-формат)
- Вложенные маршруты с Layout (project-management-формат)
- Index-маршруты
- Фильтрацию Layout/Wrapper-компонентов
- Отсутствие дублей
- Отсутствие динамических сегментов (:id, *)
- Восстановление абсолютных путей
"""

import sys
import os
import tempfile
import textwrap
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.react_parser import parse_jsx_routes


def _make_project(content: str, filename: str = 'src/App.jsx') -> str:
    """Создаёт временную директорию с файлом проекта."""
    tmp = tempfile.mkdtemp()
    filepath = Path(tmp) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding='utf-8')
    return tmp


# ─────────────────────────────────────────────────────────────────
# Тест 1: Плоские маршруты — реальный burakorkmez
# ─────────────────────────────────────────────────────────────────

BURAKORKMEZ_APP = textwrap.dedent("""\
    import { Route, Routes } from "react-router-dom";
    import Sidebar from "./components/common/Sidebar";
    import OverviewPage from "./pages/OverviewPage";
    import ProductsPage from "./pages/ProductsPage";
    import UsersPage from "./pages/UsersPage";
    import SalesPage from "./pages/SalesPage";
    import OrdersPage from "./pages/OrdersPage";
    import AnalyticsPage from "./pages/AnalyticsPage";
    import SettingsPage from "./pages/SettingsPage";

    function App() {
        return (
            <div>
                <Sidebar />
                <Routes>
                    <Route path='/' element={<OverviewPage />} />
                    <Route path='/products' element={<ProductsPage />} />
                    <Route path='/users' element={<UsersPage />} />
                    <Route path='/sales' element={<SalesPage />} />
                    <Route path='/orders' element={<OrdersPage />} />
                    <Route path='/analytics' element={<AnalyticsPage />} />
                    <Route path='/settings' element={<SettingsPage />} />
                </Routes>
            </div>
        );
    }
""")


def test_flat_routes_count():
    """7 плоских маршрутов без Layout."""
    tmp = _make_project(BURAKORKMEZ_APP)
    routes = parse_jsx_routes(tmp)
    paths = [r['path'] for r in routes]
    assert len(routes) == 7, f"Ожидалось 7, получено {len(routes)}: {paths}"
    print(f"  PASS test_flat_routes_count: {len(routes)} маршрутов")


def test_flat_routes_paths():
    """Все ожидаемые пути присутствуют."""
    tmp = _make_project(BURAKORKMEZ_APP)
    routes = parse_jsx_routes(tmp)
    paths = {r['path'] for r in routes}
    expected = {'/', '/products', '/users', '/sales', '/orders', '/analytics', '/settings'}
    assert paths == expected, f"Пути: {paths}"
    print(f"  PASS test_flat_routes_paths: {sorted(paths)}")


def test_flat_routes_components():
    """Компоненты правильно извлечены."""
    tmp = _make_project(BURAKORKMEZ_APP)
    routes = parse_jsx_routes(tmp)
    comp_map = {r['path']: r['component'] for r in routes}
    assert comp_map['/'] == 'OverviewPage', comp_map['/']
    assert comp_map['/products'] == 'ProductsPage', comp_map['/products']
    assert comp_map['/users'] == 'UsersPage', comp_map['/users']
    print(f"  PASS test_flat_routes_components")


def test_no_duplicates_flat():
    """Нет дублирующихся путей."""
    tmp = _make_project(BURAKORKMEZ_APP)
    routes = parse_jsx_routes(tmp)
    paths = [r['path'] for r in routes]
    assert len(paths) == len(set(paths)), f"Дубли: {paths}"
    print(f"  PASS test_no_duplicates_flat")


# ─────────────────────────────────────────────────────────────────
# Тест 2: Вложенные маршруты — реальный project-management
# ─────────────────────────────────────────────────────────────────

PROJECT_MGMT_APP = textwrap.dedent("""\
    import { Routes, Route } from "react-router-dom";
    import Layout from "./pages/Layout";
    import Dashboard from "./pages/Dashboard";
    import Projects from "./pages/Projects";
    import Team from "./pages/Team";
    import ProjectDetails from "./pages/ProjectDetails";
    import TaskDetails from "./pages/TaskDetails";

    const App = () => {
        return (
            <>
                <Routes>
                    <Route path="/" element={<Layout />}>
                        <Route index element={<Dashboard />} />
                        <Route path="team" element={<Team />} />
                        <Route path="projects" element={<Projects />} />
                        <Route path="projectsDetail" element={<ProjectDetails />} />
                        <Route path="taskDetails" element={<TaskDetails />} />
                    </Route>
                </Routes>
            </>
        );
    };
""")


def test_nested_layout_excluded():
    """Layout-компонент не попадает в результат."""
    tmp = _make_project(PROJECT_MGMT_APP)
    routes = parse_jsx_routes(tmp)
    components = [r['component'] for r in routes]
    assert 'Layout' not in components, f"Layout не должен быть в маршрутах: {components}"
    print(f"  PASS test_nested_layout_excluded")


def test_index_route_path():
    """Index-маршрут получает путь родителя '/'."""
    tmp = _make_project(PROJECT_MGMT_APP)
    routes = parse_jsx_routes(tmp)
    paths = {r['path'] for r in routes}
    assert '/' in paths, f"Нет index-маршрута '/': {paths}"
    index_route = next(r for r in routes if r['path'] == '/')
    assert index_route['component'] == 'Dashboard', index_route
    print(f"  PASS test_index_route_path: {index_route}")


def test_nested_absolute_paths():
    """Вложенные пути восстанавливаются до абсолютных."""
    tmp = _make_project(PROJECT_MGMT_APP)
    routes = parse_jsx_routes(tmp)
    paths = {r['path'] for r in routes}
    expected = {'/', '/team', '/projects', '/projectsDetail', '/taskDetails'}
    assert paths == expected, f"Получено: {sorted(paths)}, ожидалось: {sorted(expected)}"
    print(f"  PASS test_nested_absolute_paths: {sorted(paths)}")


def test_nested_count():
    """Ровно 5 маршрутов (без Layout)."""
    tmp = _make_project(PROJECT_MGMT_APP)
    routes = parse_jsx_routes(tmp)
    assert len(routes) == 5, f"Ожидалось 5, получено {len(routes)}: {[r['path'] for r in routes]}"
    print(f"  PASS test_nested_count: {len(routes)} маршрутов")


def test_no_duplicates_nested():
    """Нет дублирующихся путей в nested-структуре."""
    tmp = _make_project(PROJECT_MGMT_APP)
    routes = parse_jsx_routes(tmp)
    paths = [r['path'] for r in routes]
    assert len(paths) == len(set(paths)), f"Дубли: {paths}"
    print(f"  PASS test_no_duplicates_nested")


# ─────────────────────────────────────────────────────────────────
# Тест 3: Дополнительные граничные случаи
# ─────────────────────────────────────────────────────────────────

DYNAMIC_ROUTES = textwrap.dedent("""\
    import { Routes, Route } from "react-router-dom";
    import UserList from "./UserList";
    import UserDetail from "./UserDetail";
    import NotFound from "./NotFound";

    function App() {
        return (
            <Routes>
                <Route path="/users" element={<UserList />} />
                <Route path="/users/:id" element={<UserDetail />} />
                <Route path="*" element={<NotFound />} />
            </Routes>
        );
    }
""")


def test_dynamic_segments_excluded():
    """:id и * не попадают в результат."""
    tmp = _make_project(DYNAMIC_ROUTES)
    routes = parse_jsx_routes(tmp)
    paths = {r['path'] for r in routes}
    assert '/users/:id' not in paths, "Динамический маршрут не должен включаться"
    assert '*' not in paths, "Catch-all маршрут не должен включаться"
    assert '/users' in paths, f"Статический /users должен быть: {paths}"
    print(f"  PASS test_dynamic_segments_excluded: {sorted(paths)}")


PROTECTED_ROUTES = textwrap.dedent("""\
    import { Routes, Route } from "react-router-dom";
    import ProtectedLayout from "./ProtectedLayout";
    import AuthGuard from "./AuthGuard";
    import Dashboard from "./Dashboard";
    import Profile from "./Profile";

    function App() {
        return (
            <Routes>
                <Route element={<AuthGuard />}>
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/profile" element={<Profile />} />
                </Route>
            </Routes>
        );
    }
""")


def test_guard_wrapper_excluded():
    """AuthGuard без path не попадает в результат."""
    tmp = _make_project(PROTECTED_ROUTES)
    routes = parse_jsx_routes(tmp)
    components = [r['component'] for r in routes]
    assert 'AuthGuard' not in components, f"AuthGuard не должен быть в маршрутах: {components}"
    print(f"  PASS test_guard_wrapper_excluded: {components}")


def test_no_route_file():
    """Проект без react-router-dom возвращает пустой список."""
    content = textwrap.dedent("""\
        import React from 'react';
        function App() { return <div>Hello</div>; }
    """)
    tmp = _make_project(content)
    routes = parse_jsx_routes(tmp)
    assert routes == [], f"Ожидался пустой список: {routes}"
    print(f"  PASS test_no_route_file")


def test_names_not_empty():
    """Все маршруты имеют непустое имя."""
    tmp = _make_project(BURAKORKMEZ_APP)
    routes = parse_jsx_routes(tmp)
    for r in routes:
        assert r['name'], f"Пустое имя у маршрута {r}"
    print(f"  PASS test_names_not_empty")


def test_double_import_no_duplicate():
    """Если один компонент стоит дважды — дубль пути не допускается."""
    content = textwrap.dedent("""\
        import { Routes, Route } from "react-router-dom";
        import Dashboard from "./Dashboard";

        function App() {
            return (
                <Routes>
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                </Routes>
            );
        }
    """)
    tmp = _make_project(content)
    routes = parse_jsx_routes(tmp)
    paths = [r['path'] for r in routes]
    assert paths.count('/dashboard') == 1, f"Дубль /dashboard: {paths}"
    print(f"  PASS test_double_import_no_duplicate")


# ─────────────────────────────────────────────────────────────────
# Запуск всех тестов
# ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        # Flat (burakorkmez)
        test_flat_routes_count,
        test_flat_routes_paths,
        test_flat_routes_components,
        test_no_duplicates_flat,
        # Nested (project management)
        test_nested_layout_excluded,
        test_index_route_path,
        test_nested_absolute_paths,
        test_nested_count,
        test_no_duplicates_nested,
        # Edge cases
        test_dynamic_segments_excluded,
        test_guard_wrapper_excluded,
        test_no_route_file,
        test_names_not_empty,
        test_double_import_no_duplicate,
    ]

    passed = 0
    failed = 0
    errors = []

    print(f"\n{'='*60}")
    print("parse_jsx_routes() — тесты React Router v6")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  FAIL {test.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Итого: {passed} прошли, {failed} провалились из {len(tests)}")
    if errors:
        print("\nПровалившиеся:")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
