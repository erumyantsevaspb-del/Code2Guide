"""
Тесты новых возможностей парсеров:
- parse_routepath_routes: computed keys [AppRoutes.KEY]
- parse_jsx_routes: старый синтаксис component={X} и react-router v7
- parse_nextjs_pages_routes: Pages Router
- parse_component_pages_fallback: эвристика по структуре
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.react_parser import (
    parse_routepath_routes,
    parse_jsx_routes,
    parse_nextjs_routes,
    parse_nextjs_pages_routes,
    parse_react_admin_routes,
    parse_component_pages_fallback,
)


def _make_project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── parse_routepath_routes: computed keys ────────────────────────────

def test_routepath_computed_keys():
    """[AppRoutes.MAIN]: '/' — должен находиться."""
    src = _make_project({'src/router.ts': '''
import { AppRoutes } from "./appRoutes";

export const RoutePath: Record<AppRoutes, string> = {
  [AppRoutes.MAIN]: '/',
  [AppRoutes.DASHBOARD]: '/dashboard',
  [AppRoutes.SETTINGS]: '/settings',
};
'''})
    routes = parse_routepath_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"Главная не найдена: {paths}"
    assert '/dashboard' in paths, f"Dashboard не найден: {paths}"
    assert '/settings' in paths, f"Settings не найден: {paths}"
    print(f"  PASS test_routepath_computed_keys: {paths}")


def test_routepath_mixed_keys():
    """Смесь обычных и computed keys — все найдены."""
    src = _make_project({'src/routes.ts': '''
export const RoutePath = {
  home: '/',
  [UserRoutes.PROFILE]: '/profile',
};
'''})
    routes = parse_routepath_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths
    assert '/profile' in paths
    print(f"  PASS test_routepath_mixed_keys: {paths}")


# ── parse_jsx_routes: old component= syntax ──────────────────────────

def test_jsx_old_component_syntax():
    """<Route path="/" component={Home} /> — React Router v4/v5."""
    src = _make_project({'src/App.jsx': '''
import { BrowserRouter, Route, Switch } from "react-router-dom";
import Home from "./pages/Home";
import About from "./pages/About";

const App = () => (
  <BrowserRouter>
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/about" component={About} />
    </Switch>
  </BrowserRouter>
);
'''})
    routes = parse_jsx_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"Главная не найдена: {paths}"
    assert '/about' in paths, f"/about не найден: {paths}"
    print(f"  PASS test_jsx_old_component_syntax: {paths}")


def test_jsx_react_router_v7_import():
    """<Route> с импортом из react-router (без -dom, v7)."""
    src = _make_project({'src/App.tsx': '''
import { BrowserRouter, Routes, Route } from "react-router";
import Dashboard from "./Dashboard";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
'''})
    routes = parse_jsx_routes(src)
    paths = [r['path'] for r in routes]
    assert '/dashboard' in paths, f"/dashboard не найден: {paths}"
    print(f"  PASS test_jsx_react_router_v7_import: {paths}")


# ── parse_nextjs_pages_routes ────────────────────────────────────────

def test_nextjs_pages_basic():
    """pages/index.tsx → /, pages/about.tsx → /about."""
    src = _make_project({
        'pages/index.tsx': 'export default function Home() {}',
        'pages/about.tsx': 'export default function About() {}',
        'pages/dashboard.tsx': 'export default function Dashboard() {}',
    })
    routes = parse_nextjs_pages_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"Главная не найдена: {paths}"
    assert '/about' in paths, f"/about не найден: {paths}"
    assert '/dashboard' in paths, f"/dashboard не найден: {paths}"
    print(f"  PASS test_nextjs_pages_basic: {paths}")


def test_nextjs_pages_excludes_underscore():
    """pages/_app.tsx и pages/_document.tsx исключаются."""
    src = _make_project({
        'pages/_app.tsx': 'export default function App() {}',
        'pages/_document.tsx': 'export default function Document() {}',
        'pages/index.tsx': 'export default function Home() {}',
    })
    routes = parse_nextjs_pages_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths
    assert len(routes) == 1, f"Ожидался 1 маршрут: {paths}"
    print(f"  PASS test_nextjs_pages_excludes_underscore: {paths}")


def test_nextjs_pages_excludes_api():
    """pages/api/ исключается."""
    src = _make_project({
        'pages/api/users.ts': 'export default function handler() {}',
        'pages/index.tsx': 'export default function Home() {}',
    })
    routes = parse_nextjs_pages_routes(src)
    paths = [r['path'] for r in routes]
    assert '/api/users' not in paths, f"API роут не должен попасть: {paths}"
    assert '/' in paths
    print(f"  PASS test_nextjs_pages_excludes_api: {paths}")


def test_nextjs_pages_excludes_dynamic():
    """pages/[id].tsx исключается (динамический сегмент)."""
    src = _make_project({
        'pages/index.tsx': 'export default function Home() {}',
        'pages/[id].tsx': 'export default function Detail() {}',
    })
    routes = parse_nextjs_pages_routes(src)
    paths = [r['path'] for r in routes]
    assert '/[id]' not in paths, f"Динамический сегмент не должен попасть: {paths}"
    assert len(routes) == 1
    print(f"  PASS test_nextjs_pages_excludes_dynamic: {paths}")


# ── parse_component_pages_fallback ───────────────────────────────────

def test_fallback_finds_pages():
    """src/pages/ файлы → приблизительные маршруты."""
    src = _make_project({
        'src/pages/DashboardPage.tsx': 'export default function Dashboard() {}',
        'src/pages/SettingsPage.tsx': 'export default function Settings() {}',
    })
    routes = parse_component_pages_fallback(src)
    paths = [r['path'] for r in routes]
    assert any('dashboard' in p for p in paths), f"dashboard не найден: {paths}"
    assert any('settings' in p for p in paths), f"settings не найден: {paths}"
    for r in routes:
        assert r.get('approximate') is True, f"Флаг approximate не выставлен: {r}"
    print(f"  PASS test_fallback_finds_pages: {paths}")


def test_fallback_skips_layout():
    """IndexPage, AppPage, LayoutPage — исключаются."""
    src = _make_project({
        'src/pages/IndexPage.tsx': 'export default function Index() {}',
        'src/pages/AppPage.tsx': 'export default function App() {}',
        'src/pages/DashboardPage.tsx': 'export default function Dashboard() {}',
    })
    routes = parse_component_pages_fallback(src)
    paths = [r['path'] for r in routes]
    assert '/index' not in paths and '/' not in paths, f"Index не должен попасть: {paths}"
    assert any('dashboard' in p for p in paths)
    print(f"  PASS test_fallback_skips_layout: {paths}")


def test_fallback_empty_when_no_dirs():
    """Нет src/pages/, src/views/, src/screens/ → пустой список."""
    src = _make_project({'src/components/Button.tsx': 'export const Button = () => null;'})
    routes = parse_component_pages_fallback(src)
    assert routes == [], f"Должен быть пустой: {routes}"
    print(f"  PASS test_fallback_empty_when_no_dirs")


# ── R4/R5: регрессионные тесты парсеров ──────────────────────────────

def test_r4_nextjs_app_router_regression():
    """R4: parse_nextjs_routes находит страницы в app/ (Next.js App Router)."""
    src = _make_project({
        'app/page.tsx': 'export default function Home() { return <h1>Home</h1>; }',
        'app/dashboard/page.tsx': 'export default function Dashboard() { return <h1>Dash</h1>; }',
    })
    routes = parse_nextjs_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"R4 FAIL: нет '/' в {paths}"
    assert '/dashboard' in paths, f"R4 FAIL: нет '/dashboard' в {paths}"
    print(f"  PASS test_r4_nextjs_app_router_regression: {paths}")


def test_r5_react_admin_regression():
    """R5: parse_react_admin_routes находит <Resource name="..."> маршруты."""
    src = _make_project({'src/App.tsx': '''
import { Admin, Resource } from "react-admin";
import PostList from "./PostList";
import UserList from "./UserList";

export const App = () => (
  <Admin>
    <Resource name="posts" list={PostList} />
    <Resource name="users" list={UserList} />
  </Admin>
);
'''})
    routes = parse_react_admin_routes(src)
    paths = [r['path'] for r in routes]
    assert '/posts' in paths, f"R5 FAIL: нет '/posts' в {paths}"
    assert '/users' in paths, f"R5 FAIL: нет '/users' в {paths}"
    print(f"  PASS test_r5_react_admin_regression: {paths}")


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import shutil
    tests = [
        test_routepath_computed_keys,
        test_routepath_mixed_keys,
        test_jsx_old_component_syntax,
        test_jsx_react_router_v7_import,
        test_nextjs_pages_basic,
        test_nextjs_pages_excludes_underscore,
        test_nextjs_pages_excludes_api,
        test_nextjs_pages_excludes_dynamic,
        test_fallback_finds_pages,
        test_fallback_skips_layout,
        test_fallback_empty_when_no_dirs,
        test_r4_nextjs_app_router_regression,
        test_r5_react_admin_regression,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("Новые парсеры — тесты")
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
