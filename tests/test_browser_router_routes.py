"""
Тесты parse_browser_router_routes() — поддержка createBrowserRouter.

Проверяем:
- Обычный маршрут "/" с Component: HomePage
- Маршрут с полем element вместо Component
- Импорт из "react-router" (v7)
- Импорт из "react-router-dom" (v6)
- Исключение catch-all "*"
- Исключение динамических маршрутов ":id"
- Исключение Layout/Guard компонентов
- Переменная: const routes = [...]; createBrowserRouter(routes)
- Несколько маршрутов — все обнаружены
- Отсутствие createBrowserRouter — пустой список
- Пустой массив маршрутов — пустой список
- Дедупликация одинаковых путей
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.react_parser import parse_browser_router_routes


def _make_project(files: dict) -> str:
    """Создаёт временную директорию с заданными файлами, возвращает путь."""
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── Базовые случаи ────────────────────────────────────────────────

def test_component_field_react_router():
    """Component: HomePage + import react-router → маршрут найден."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
import HomePage from "./pages/HomePage.tsx";

export const router = createBrowserRouter([
  { path: "/", Component: HomePage },
]);
'''})
    routes = parse_browser_router_routes(src)
    assert len(routes) == 1, f"Ожидался 1 маршрут, получено {len(routes)}: {routes}"
    assert routes[0]['path'] == '/'
    assert routes[0]['component'] == 'HomePage'
    print(f"  PASS test_component_field_react_router: {routes}")


def test_element_field_react_router_dom():
    """element: <Dashboard /> + import react-router-dom → маршрут найден."""
    src = _make_project({'src/App.jsx': '''
import { createBrowserRouter } from "react-router-dom";
import Dashboard from "./Dashboard";

const router = createBrowserRouter([
  { path: "/dashboard", element: <Dashboard /> },
]);
'''})
    routes = parse_browser_router_routes(src)
    assert len(routes) == 1, f"{routes}"
    assert routes[0]['path'] == '/dashboard'
    assert routes[0]['component'] == 'Dashboard'
    print(f"  PASS test_element_field_react_router_dom: {routes}")


def test_import_from_react_router_v7():
    """Пакет 'react-router' (без -dom, v7) — маршруты находятся."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
export const router = createBrowserRouter([
  { path: "/home", Component: HomeView },
]);
'''})
    routes = parse_browser_router_routes(src)
    assert routes, "Должен найти маршрут из react-router v7"
    assert routes[0]['path'] == '/home'
    print(f"  PASS test_import_from_react_router_v7: {routes}")


def test_import_from_react_router_dom():
    """Пакет 'react-router-dom' (v6) — маршруты находятся."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router-dom";
export const router = createBrowserRouter([
  { path: "/profile", Component: ProfilePage },
]);
'''})
    routes = parse_browser_router_routes(src)
    assert routes, "Должен найти маршрут из react-router-dom"
    assert routes[0]['path'] == '/profile'
    print(f"  PASS test_import_from_react_router_dom: {routes}")


# ── Фильтрация ────────────────────────────────────────────────────

def test_catch_all_excluded():
    """path: \"*\" исключается."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
export const router = createBrowserRouter([
  { path: "/", Component: HomePage },
  { path: "*", Component: NotFoundPage },
]);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '*' not in paths, f"'*' не должен быть в маршрутах: {paths}"
    assert '/' in paths
    assert len(routes) == 1, f"Ожидался 1 маршрут (без catch-all): {routes}"
    print(f"  PASS test_catch_all_excluded: {paths}")


def test_dynamic_segment_excluded():
    """path с :param исключается."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
export const router = createBrowserRouter([
  { path: "/users", Component: UsersList },
  { path: "/users/:id", Component: UserDetail },
]);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '/users/:id' not in paths, f"Динамический маршрут не должен попасть: {paths}"
    assert '/users' in paths
    print(f"  PASS test_dynamic_segment_excluded: {paths}")


def test_layout_component_excluded():
    """Компоненты с именами Layout/Guard/PrivateRoute исключаются."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
export const router = createBrowserRouter([
  { path: "/", Component: RootLayout },
  { path: "/home", Component: HomePage },
  { path: "/admin", Component: AuthGuard },
]);
'''})
    routes = parse_browser_router_routes(src)
    components = [r['component'] for r in routes]
    assert 'RootLayout' not in components, f"Layout не должен быть в маршрутах: {components}"
    assert 'AuthGuard' not in components, f"Guard не должен быть в маршрутах: {components}"
    assert 'HomePage' in components
    print(f"  PASS test_layout_component_excluded: {components}")


# ── Переменная ────────────────────────────────────────────────────

def test_variable_routes():
    """const routes = [...]; createBrowserRouter(routes) — маршруты найдены."""
    src = _make_project({'src/router.ts': '''
import { createBrowserRouter } from "react-router-dom";

const routes = [
  { path: "/", Component: App },
  { path: "/about", Component: About },
];

export const router = createBrowserRouter(routes);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths and '/about' in paths, f"Должны найтись оба маршрута: {paths}"
    print(f"  PASS test_variable_routes: {paths}")


# ── Несколько маршрутов ───────────────────────────────────────────

def test_multiple_routes():
    """React Starter реальный файл: 2 маршрута, catch-all отфильтрован."""
    content = '''
import { createBrowserRouter } from "react-router";
import HomePage from "./pages/HomePage.tsx";
import NotFoundPage from "./pages/NotFoundPage.tsx";

export const router = createBrowserRouter([
  { path: "/", Component: HomePage },
  { path: "*", Component: NotFoundPage },
]);
'''
    src = _make_project({'src/router.tsx': content})
    routes = parse_browser_router_routes(src)
    assert len(routes) == 1, f"Ожидался 1 (без '*'): {routes}"
    assert routes[0]['path'] == '/'
    assert routes[0]['component'] == 'HomePage'
    print(f"  PASS test_multiple_routes (React Starter реальный): {routes}")


# ── Ложные срабатывания ───────────────────────────────────────────

def test_no_create_browser_router_returns_empty():
    """Файл без createBrowserRouter → пустой список."""
    src = _make_project({'src/App.jsx': '''
import { BrowserRouter, Route } from "react-router-dom";
const App = () => <BrowserRouter><Route path="/" element={<Home />} /></BrowserRouter>;
'''})
    routes = parse_browser_router_routes(src)
    assert routes == [], f"Должен быть пустой список: {routes}"
    print(f"  PASS test_no_create_browser_router_returns_empty")


def test_empty_routes_array():
    """createBrowserRouter([]) → пустой список."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router";
export const router = createBrowserRouter([]);
'''})
    routes = parse_browser_router_routes(src)
    assert routes == [], f"Пустой массив → пустой результат: {routes}"
    print(f"  PASS test_empty_routes_array")


def test_no_react_router_import_returns_empty():
    """createBrowserRouter без импорта react-router → пустой список."""
    src = _make_project({'src/router.tsx': '''
// custom createBrowserRouter utility (not react-router)
import { createBrowserRouter } from "./custom-router";
export const router = createBrowserRouter([
  { path: "/", Component: App },
]);
'''})
    routes = parse_browser_router_routes(src)
    assert routes == [], f"Без импорта react-router должен быть пустой список: {routes}"
    print(f"  PASS test_no_react_router_import_returns_empty")


def test_deduplication():
    """Дублирующийся путь включается только один раз."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router-dom";
export const router = createBrowserRouter([
  { path: "/home", Component: Home },
  { path: "/home", Component: HomeAlias },
]);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert paths.count('/home') == 1, f"Дубль не должен повторяться: {paths}"
    print(f"  PASS test_deduplication: {paths}")


# ── W4 regression: TypeScript type annotation RouteObject[] ──────

def test_w4_type_annotation_variable():
    """R1: const routes: RouteObject[] = [...]; createBrowserRouter(routes) → маршрут найден.

    До исправления W4 parse_browser_router_routes находил '[' в 'RouteObject[]'
    вместо начала массива, извлекал пустой блок и возвращал [].
    """
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter, RouteObject } from "react-router-dom";
import Dashboard from "./Dashboard";

const routes: RouteObject[] = [
  { path: "/dashboard", element: <Dashboard /> },
];

export const router = createBrowserRouter(routes);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '/dashboard' in paths, f"R1 FAIL: ожидался '/dashboard', получено {routes}"
    print(f"  PASS test_w4_type_annotation_variable: {routes}")


def test_w4_no_annotation_still_works():
    """R2: без аннотации типа — маршрут найден (регрессия не введена)."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router-dom";
import Users from "./Users";

const routes = [
  { path: "/users", element: <Users /> },
];

export const router = createBrowserRouter(routes);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '/users' in paths, f"R2 FAIL: ожидался '/users', получено {routes}"
    print(f"  PASS test_w4_no_annotation_still_works: {routes}")


def test_w4_inline_array_unaffected():
    """R3: инлайн createBrowserRouter([...]) без переменной — маршрут найден."""
    src = _make_project({'src/router.tsx': '''
import { createBrowserRouter } from "react-router-dom";
import Home from "./Home";

export const router = createBrowserRouter([
  { path: "/", element: <Home /> },
]);
'''})
    routes = parse_browser_router_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"R3 FAIL: ожидался '/', получено {routes}"
    print(f"  PASS test_w4_inline_array_unaffected: {routes}")


# ── Runner ────────────────────────────────────────────────────────

if __name__ == '__main__':
    import shutil
    tests = [
        test_component_field_react_router,
        test_element_field_react_router_dom,
        test_import_from_react_router_v7,
        test_import_from_react_router_dom,
        test_catch_all_excluded,
        test_dynamic_segment_excluded,
        test_layout_component_excluded,
        test_variable_routes,
        test_multiple_routes,
        test_no_create_browser_router_returns_empty,
        test_empty_routes_array,
        test_no_react_router_import_returns_empty,
        test_deduplication,
        test_w4_type_annotation_variable,
        test_w4_no_annotation_still_works,
        test_w4_inline_array_unaffected,
    ]

    passed = failed = 0
    errors = []

    print(f"\n{'='*60}")
    print("parse_browser_router_routes() -- tests")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)}")
    if errors:
        print("\nFailed:")
        for name, err in errors:
            print(f"  {name}: {err}")
    print(f"{'='*60}\n")

    import sys
    sys.exit(0 if failed == 0 else 1)
