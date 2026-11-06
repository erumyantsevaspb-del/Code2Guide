"""
Тесты parse_router_config_full: извлечение route_key -> file_path из router.config.tsx.

Паттерны:
  1. p22: прямые относительные импорты pages/*, widgets/*
  2. ЛК: barrel-alias @lab -> tsconfig -> lazy import
"""

import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.route_config_parser import (
    parse_router_config_full,
    _extract_imports,
    _extract_route_entries,
    _read_tsconfig_aliases,
)


def _make_project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── unit: _extract_imports ─────────────────────────────────────────────────

def test_extract_imports_named():
    content = 'import { ChartsPage } from "pages/charts";'
    result = _extract_imports(content)
    assert result.get('ChartsPage') == 'pages/charts', f"Got: {result}"
    print("  PASS test_extract_imports_named")


def test_extract_imports_default():
    content = 'import ChartsPage from "pages/charts";'
    result = _extract_imports(content)
    assert result.get('ChartsPage') == 'pages/charts', f"Got: {result}"
    print("  PASS test_extract_imports_default")


def test_extract_imports_multi_named():
    content = 'import { AlignerFormPage, CrownPage } from "@lab";'
    result = _extract_imports(content)
    assert result.get('AlignerFormPage') == '@lab'
    assert result.get('CrownPage') == '@lab'
    print("  PASS test_extract_imports_multi_named")


# ── unit: _extract_route_entries ──────────────────────────────────────────

def test_extract_route_entries_routepath():
    content = """
    {
        path: RoutePath.appoints,
        element: <AppointsPage />,
    },
    """
    result = _extract_route_entries(content)
    assert result.get('appoints') == 'AppointsPage', f"Got: {result}"
    print("  PASS test_extract_route_entries_routepath")


def test_extract_route_entries_approutes():
    content = """
    [AppRoutes.LAB]: {
        path: RoutePath.lab,
        element: <LabPage />,
    },
    """
    result = _extract_route_entries(content)
    assert result.get('lab') == 'LabPage', f"Got: {result}"
    print("  PASS test_extract_route_entries_approutes")


def test_extract_route_entries_multiple():
    content = """
    { path: RoutePath.home, element: <ChartsPage /> },
    { path: RoutePath.patients, element: <PatientAppoints /> },
    """
    result = _extract_route_entries(content)
    assert result.get('home') == 'ChartsPage'
    assert result.get('patients') == 'PatientAppoints'
    print("  PASS test_extract_route_entries_multiple")


# ── unit: _read_tsconfig_aliases ─────────────────────────────────────────

def test_tsconfig_aliases():
    src = _make_project({
        'tsconfig.base.json': json.dumps({
            "compilerOptions": {
                "paths": {
                    "@lab": ["apps/lab/src/index.ts"],
                    "@main": ["apps/main/src/index.ts"],
                }
            }
        })
    })
    aliases = _read_tsconfig_aliases(Path(src))
    assert aliases.get('@lab') == 'apps/lab/src/index', f"Got: {aliases}"
    assert aliases.get('@main') == 'apps/main/src/index'
    print("  PASS test_tsconfig_aliases")


# ── integration: p22 pattern ─────────────────────────────────────────────

def test_p22_direct_import():
    """p22: import { ChartsPage } from 'pages/charts' -> pages/charts.page.tsx"""
    src = _make_project({
        'apps/crm/src/app/providers/app.router/config/router.config.tsx': (
            'import { ChartsPage } from "pages/charts";\n'
            'const routes = [{ path: RoutePath.home, element: <ChartsPage /> }];'
        ),
        'apps/crm/src/pages/charts/charts.page.tsx': 'export default function ChartsPage() {}',
    })
    result = parse_router_config_full(src)
    assert 'home' in result, f"route 'home' not found, got: {list(result.keys())}"
    assert result['home'].name == 'charts.page.tsx', f"Got: {result['home']}"
    print(f"  PASS test_p22_direct_import: {result['home']}")


def test_p22_widget_import():
    """p22: import { PatientAppoints } from 'widgets/appoints/patient.appoints'"""
    src = _make_project({
        'apps/crm/src/app/providers/app.router/config/router.config.tsx': (
            'import { PatientAppoints } from "widgets/appoints/patient.appoints";\n'
            'const routes = [{ path: RoutePath.patients, element: <PatientAppoints /> }];'
        ),
        'apps/crm/src/widgets/appoints/patient.appoints.tsx': 'export function PatientAppoints() {}',
    })
    result = parse_router_config_full(src)
    assert 'patients' in result, f"route 'patients' not found, got: {list(result.keys())}"
    assert result['patients'].name == 'patient.appoints.tsx'
    print(f"  PASS test_p22_widget_import: {result['patients']}")


# ── integration: LK barrel pattern ───────────────────────────────────────

def test_lk_barrel_lazy_import():
    """ЛК: @lab -> barrel index.ts -> lazy import -> aligner-form.page.tsx"""
    src = _make_project({
        'tsconfig.base.json': json.dumps({
            "compilerOptions": {
                "paths": {"@lab": ["apps/lab/src/index.ts"]}
            }
        }),
        'apps/shell/src/app/providers/router/config/router.config.tsx': (
            'import { AlignerFormPage } from "@lab";\n'
            '[AppRoutes.ALIGNER]: { path: RoutePath.aligner, element: <AlignerFormPage /> },'
        ),
        'apps/lab/src/index.ts': (
            'export const AlignerFormPage = lazy(() => '
            'import("./pages/aligner/aligner-form/ui/aligner-form.page"));\n'
        ),
        'apps/lab/src/pages/aligner/aligner-form/ui/aligner-form.page.tsx': (
            'export default function AlignerFormPage() {}'
        ),
    })
    result = parse_router_config_full(src)
    assert 'aligner' in result, f"route 'aligner' not found, got: {list(result.keys())}"
    assert result['aligner'].name == 'aligner-form.page.tsx'
    print(f"  PASS test_lk_barrel_lazy_import: {result['aligner']}")


def test_no_config_returns_empty():
    """Проект без router.config.tsx -> пустой результат."""
    src = _make_project({'src/pages/Home.tsx': 'export default function Home() {}'})
    result = parse_router_config_full(src)
    assert result == {}, f"Expected empty, got: {result}"
    print("  PASS test_no_config_returns_empty")


def test_unresolvable_import_skipped():
    """Импорт, указывающий на несуществующий файл -> маршрут не попадает в результат."""
    src = _make_project({
        'apps/crm/src/app/router.config.tsx': (
            'import { MissingPage } from "pages/missing";\n'
            'const routes = [{ path: RoutePath.missing, element: <MissingPage /> }];'
        ),
    })
    result = parse_router_config_full(src)
    assert 'missing' not in result, f"Should not resolve missing file: {result}"
    print("  PASS test_unresolvable_import_skipped")


# ── runner ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_extract_imports_named,
        test_extract_imports_default,
        test_extract_imports_multi_named,
        test_extract_route_entries_routepath,
        test_extract_route_entries_approutes,
        test_extract_route_entries_multiple,
        test_tsconfig_aliases,
        test_p22_direct_import,
        test_p22_widget_import,
        test_lk_barrel_lazy_import,
        test_no_config_returns_empty,
        test_unresolvable_import_skipped,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("route_config_parser — тесты")
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
