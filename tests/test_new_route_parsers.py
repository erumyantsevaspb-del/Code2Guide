"""
Регрессионные тесты новых парсеров маршрутов:
- parse_distributed_router_files  (p24 — React Admin Dashboard larry-xue)
- parse_paths_config_routes        (p20 — Bulletproof React monorepo)
- parse_remix_flat_routes          (p27 — React Router SaaS Template)

Синтетические входные данные воспроизводят реальную структуру этих проектов.
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
    parse_distributed_router_files,
    parse_paths_config_routes,
    parse_remix_flat_routes,
)


def _make_project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── parse_distributed_router_files (p24) ─────────────────────────────

def test_p24_distributed_router_basic():
    """Находит маршруты из *.router.tsx файлов (React Admin Dashboard larry-xue)."""
    src = _make_project({
        'src/views/dashboard/dashboard.router.tsx': '''
import { lazy } from 'react';
const DashboardPage = lazy(() => import('./DashboardPage'));
export default [{ path: 'dashboard', element: <DashboardPage /> }];
''',
        'src/views/auth/auth.router.tsx': '''
export default [
  { path: 'auth/login', element: <LoginPage /> },
  { path: 'auth/register', element: <RegisterPage /> },
];
''',
        'src/views/customers/customers.router.tsx': '''
export default [{ path: 'customers', element: <CustomersPage /> }];
''',
    })
    routes = parse_distributed_router_files(src)
    paths = [r['path'] for r in routes]
    assert '/dashboard' in paths, f"dashboard не найден: {paths}"
    assert '/auth/login' in paths, f"auth/login не найден: {paths}"
    assert '/auth/register' in paths, f"auth/register не найден: {paths}"
    assert '/customers' in paths, f"customers не найден: {paths}"
    print(f"  PASS test_p24_distributed_router_basic: {paths}")


def test_p24_distributed_router_with_children():
    """Дочерние пути тоже извлекаются из *.router.tsx."""
    src = _make_project({
        'src/views/team/team.router.tsx': '''
export default [
  {
    path: 'team',
    element: <TeamLayout />,
    children: [
      { path: 'roles', element: <RolesPage /> },
    ],
  },
];
''',
    })
    routes = parse_distributed_router_files(src)
    paths = [r['path'] for r in routes]
    assert '/team' in paths, f"team не найден: {paths}"
    assert '/roles' in paths, f"roles не найден: {paths}"
    print(f"  PASS test_p24_distributed_router_with_children: {paths}")


def test_p24_distributed_router_skips_dynamic():
    """Динамические пути (:id) пропускаются."""
    src = _make_project({
        'src/views/user/user.router.tsx': '''
export default [
  { path: 'users', element: <UsersPage /> },
  { path: 'users/:id', element: <UserDetailPage /> },
];
''',
    })
    routes = parse_distributed_router_files(src)
    paths = [r['path'] for r in routes]
    assert '/users' in paths, f"users не найден: {paths}"
    assert not any(':id' in p for p in paths), f"Динамический путь не должен попасть: {paths}"
    print(f"  PASS test_p24_distributed_router_skips_dynamic: {paths}")


def test_p24_distributed_router_skips_node_modules():
    """Файлы в node_modules не обрабатываются."""
    src = _make_project({
        'node_modules/some-lib/src/router.tsx': '''
export default [{ path: 'lib-route', element: <LibPage /> }];
''',
        'src/views/home/home.router.tsx': '''
export default [{ path: 'home', element: <HomePage /> }];
''',
    })
    routes = parse_distributed_router_files(src)
    paths = [r['path'] for r in routes]
    assert '/lib-route' not in paths, f"node_modules не должен обрабатываться: {paths}"
    assert '/home' in paths, f"home не найден: {paths}"
    print(f"  PASS test_p24_distributed_router_skips_node_modules: {paths}")


def test_p24_distributed_router_empty_when_no_router_files():
    """Нет *.router.tsx файлов → пустой список."""
    src = _make_project({
        'src/App.tsx': 'export default function App() {}',
    })
    routes = parse_distributed_router_files(src)
    assert routes == [], f"Должен быть пустой: {routes}"
    print(f"  PASS test_p24_distributed_router_empty_when_no_router_files")


# ── parse_paths_config_routes (p20) ──────────────────────────────────

def test_p20_paths_config_basic():
    """Находит маршруты из paths.ts конфига (Bulletproof React)."""
    src = _make_project({
        'apps/react-vite/src/config/paths.ts': '''
export const paths = {
  home: {
    path: '/',
    getHref: () => '/',
  },
  auth: {
    register: {
      path: '/auth/register',
      getHref: () => '/auth/register',
    },
    login: {
      path: '/auth/login',
      getHref: () => '/auth/login',
    },
  },
  app: {
    root: {
      path: '/app',
      getHref: () => '/app',
    },
    dashboard: {
      path: '',
      getHref: () => '/app',
    },
    discussions: {
      path: 'discussions',
      getHref: () => '/app/discussions',
    },
    users: {
      path: 'users',
      getHref: () => '/app/users',
    },
  },
} as const;
''',
    })
    routes = parse_paths_config_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths, f"/ не найден: {paths}"
    assert '/auth/register' in paths, f"/auth/register не найден: {paths}"
    assert '/auth/login' in paths, f"/auth/login не найден: {paths}"
    assert '/app' in paths, f"/app не найден: {paths}"
    print(f"  PASS test_p20_paths_config_basic: {paths}")


def test_p20_paths_config_skips_empty():
    """Пустые path: '' значения пропускаются."""
    src = _make_project({
        'src/config/paths.ts': '''
export const paths = {
  home: { path: '/' },
  dashboard: { path: '' },
  settings: { path: '/settings' },
} as const;
''',
    })
    routes = parse_paths_config_routes(src)
    paths = [r['path'] for r in routes]
    assert '' not in paths, f"Пустой путь не должен попасть: {paths}"
    assert '/' in paths
    assert '/settings' in paths
    print(f"  PASS test_p20_paths_config_skips_empty: {paths}")


def test_p20_paths_config_requires_multiple_paths():
    """Файл с единственным path: не считается конфигом путей."""
    src = _make_project({
        'src/config/paths.ts': '''
export const authPath = { path: '/login' };
''',
    })
    routes = parse_paths_config_routes(src)
    # Одно совпадение — не конфиг, результат пустой
    assert routes == [], f"Должен быть пустой (мало совпадений): {routes}"
    print(f"  PASS test_p20_paths_config_requires_multiple_paths")


def test_p20_paths_config_skips_node_modules():
    """node_modules не обрабатываются."""
    src = _make_project({
        'node_modules/some-lib/paths.ts': '''
export const paths = { a: { path: '/a' }, b: { path: '/b' } };
''',
        'src/config/paths.ts': '''
export const paths = { home: { path: '/' }, settings: { path: '/settings' } };
''',
    })
    routes = parse_paths_config_routes(src)
    paths = [r['path'] for r in routes]
    assert '/' in paths
    assert len([r for r in routes if r['path'] == '/a']) == 0, f"node_modules не должен обрабатываться: {paths}"
    print(f"  PASS test_p20_paths_config_skips_node_modules: {paths}")


# ── parse_remix_flat_routes (p27) ─────────────────────────────────────

def test_p27_remix_flat_routes_basic():
    """Базовые маршруты из app/routes/ (React Router SaaS Template)."""
    src = _make_project({
        'app/routes/dashboard.tsx': 'export default function Dashboard() {}',
        'app/routes/settings.tsx': 'export default function Settings() {}',
        'app/routes/_index.tsx': 'export default function Home() {}',
    })
    routes = parse_remix_flat_routes(src)
    paths = [r['path'] for r in routes]
    assert '/dashboard' in paths, f"dashboard не найден: {paths}"
    assert '/settings' in paths, f"settings не найден: {paths}"
    assert '/_index' not in paths, f"_index не должен попасть как путь: {paths}"
    print(f"  PASS test_p27_remix_flat_routes_basic: {paths}")


def test_p27_remix_flat_routes_layout_prefix_excluded():
    """Сегменты с _ (layout prefix) исключаются из URL."""
    src = _make_project({
        'app/routes/_authenticated-routes+/dashboard.tsx': 'export default function Dashboard() {}',
        'app/routes/_authenticated-routes+/profile.tsx': 'export default function Profile() {}',
    })
    routes = parse_remix_flat_routes(src)
    paths = [r['path'] for r in routes]
    # Layout prefix _authenticated-routes должен быть исключён
    assert all('authenticated' not in p for p in paths), f"Layout prefix не должен быть в пути: {paths}"
    assert '/dashboard' in paths, f"dashboard не найден: {paths}"
    assert '/profile' in paths, f"profile не найден: {paths}"
    print(f"  PASS test_p27_remix_flat_routes_layout_prefix_excluded: {paths}")


def test_p27_remix_flat_routes_skips_dynamic():
    """Динамические сегменты ($param) пропускаются."""
    src = _make_project({
        'app/routes/organizations_+/$organizationSlug+/dashboard.tsx': 'export default function OrgDash() {}',
        'app/routes/settings.tsx': 'export default function Settings() {}',
    })
    routes = parse_remix_flat_routes(src)
    paths = [r['path'] for r in routes]
    assert not any(':organizationSlug' in p for p in paths), f"Динамический путь не должен попасть: {paths}"
    assert '/settings' in paths, f"settings не найден: {paths}"
    print(f"  PASS test_p27_remix_flat_routes_skips_dynamic: {paths}")


def test_p27_remix_flat_routes_empty_when_no_routes_dir():
    """Нет app/routes/ или src/routes/ → пустой список."""
    src = _make_project({
        'app/routes.ts': 'export default flatRoutes("routes", defineRoutes);',
    })
    routes = parse_remix_flat_routes(src)
    assert routes == [], f"Должен быть пустой: {routes}"
    print(f"  PASS test_p27_remix_flat_routes_empty_when_no_routes_dir")


def test_p27_remix_flat_routes_onboarding():
    """Маршруты без layout prefix (onboarding+/) — включаются с именем каталога."""
    src = _make_project({
        'app/routes/onboarding+/step1.tsx': 'export default function Step1() {}',
        'app/routes/onboarding+/step2.tsx': 'export default function Step2() {}',
    })
    routes = parse_remix_flat_routes(src)
    paths = [r['path'] for r in routes]
    # onboarding+ → onboarding, step1 включается
    assert any('onboarding' in p for p in paths), f"onboarding не найден: {paths}"
    print(f"  PASS test_p27_remix_flat_routes_onboarding: {paths}")


# ── Runner ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        # p24
        test_p24_distributed_router_basic,
        test_p24_distributed_router_with_children,
        test_p24_distributed_router_skips_dynamic,
        test_p24_distributed_router_skips_node_modules,
        test_p24_distributed_router_empty_when_no_router_files,
        # p20
        test_p20_paths_config_basic,
        test_p20_paths_config_skips_empty,
        test_p20_paths_config_requires_multiple_paths,
        test_p20_paths_config_skips_node_modules,
        # p27
        test_p27_remix_flat_routes_basic,
        test_p27_remix_flat_routes_layout_prefix_excluded,
        test_p27_remix_flat_routes_skips_dynamic,
        test_p27_remix_flat_routes_empty_when_no_routes_dir,
        test_p27_remix_flat_routes_onboarding,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("Новые парсеры p20/p24/p27 — тесты")
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
