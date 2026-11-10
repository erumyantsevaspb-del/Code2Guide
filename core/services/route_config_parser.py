"""
Парсер router.config.tsx — извлекает маппинг route_key -> file_path.

Поддерживает два паттерна:
  1. Прямые относительные импорты (p22): from "pages/charts" -> find pages/charts.tsx
  2. Barrel-aliases NX монорепо (ЛК): from "@lab" -> tsconfig -> barrel index -> lazy import path
"""

import json
import re
from pathlib import Path


def parse_router_config(repo_path: str) -> dict:
    """
    Возвращает {route_key: Path} для всех маршрутов, найденных в router.config.tsx.
    route_key — нижний регистр ключа RoutePath/AppRoutes enum.
    Если конфиг не найден или не распознан — возвращает {}.
    """
    repo = Path(repo_path)
    result = {}

    config_files = _find_config_files(repo)
    if not config_files:
        return result

    alias_map = _read_tsconfig_aliases(repo)

    for config_file in config_files:
        content = config_file.read_text(encoding='utf-8', errors='ignore')
        import_map = _extract_imports(content)
        route_to_comp = _extract_route_entries(content)

        for route_key, comp_name in route_to_comp.items():
            if route_key in result:
                continue
            module_path = import_map.get(comp_name)
            if not module_path:
                continue
            resolved = _resolve_to_file(repo, config_file.parent, module_path, alias_map)
            if resolved:
                result[route_key] = resolved

    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_config_files(repo: Path) -> list:
    found = []
    for candidate in repo.rglob('*'):
        if 'node_modules' in candidate.parts:
            continue
        if not candidate.is_file():
            continue
        name_lower = candidate.name.lower()
        if 'router.config' in name_lower and candidate.suffix in ('.tsx', '.ts'):
            found.append(candidate)
    return found


def _strip_jsonc(raw: str) -> str:
    """Убирает // комментарии и trailing commas из JSONC/tsconfig."""
    # Удаляем // комментарии вне строк
    raw = re.sub(r'//[^\n]*', '', raw)
    # Удаляем /* ... */ комментарии
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    # Удаляем trailing commas перед } или ]
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    return raw


def _read_tsconfig_aliases(repo: Path) -> dict:
    """Читает tsconfig.base.json / tsconfig.json и возвращает {alias: path_without_extension}."""
    aliases = {}
    for tsconfig_name in ('tsconfig.base.json', 'tsconfig.json'):
        tsconfig = repo / tsconfig_name
        if not tsconfig.exists():
            continue
        try:
            raw = tsconfig.read_text(encoding='utf-8', errors='ignore')
            raw = _strip_jsonc(raw)
            data = json.loads(raw)
            paths = (data.get('compilerOptions') or {}).get('paths') or {}
            for alias, targets in paths.items():
                clean_alias = alias.rstrip('/*')
                if targets and isinstance(targets, list):
                    target = targets[0].rstrip('/*')
                    target = re.sub(r'\.(tsx?|jsx?)$', '', target)
                    aliases[clean_alias] = target
            # Если нашли алиасы — прекращаем поиск
            if aliases:
                break
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning("tsconfig parse error (%s): %s", tsconfig, e)
    return aliases


def _extract_imports(content: str) -> dict:
    """Возвращает {ComponentName: module_path} из import-строк."""
    result = {}
    # import { Foo, Bar } from "path"
    # import Foo from "path"
    pattern = re.compile(
        r'import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+["\']([^"\']+)["\']'
    )
    for m in pattern.finditer(content):
        named, default, path = m.group(1), m.group(2), m.group(3)
        if default:
            result[default] = path
        if named:
            for name in re.split(r'[,\s]+', named):
                name = name.strip()
                if name:
                    result[name] = path
    return result


def _extract_route_entries(content: str) -> dict:
    """
    Извлекает {route_key: ComponentName} из JSX route-объектов.

    Паттерны:
      path: RoutePath.key        -> element: <ComponentName>
      [AppRoutes.KEY]: { ... element: <ComponentName> }
    """
    result = {}

    # Паттерн: path: RoutePath.key ... element: <CompName>
    # Ищем блок маршрута (между { и }) чтобы не смешивать ключи разных маршрутов
    block_pattern = re.compile(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', re.DOTALL)
    for block_m in block_pattern.finditer(content):
        block = block_m.group(1)
        key_m = re.search(r'RoutePath\.(\w+)', block)
        comp_m = re.search(r'element:\s*<(\w+)', block)
        if key_m and comp_m:
            result[key_m.group(1).lower()] = comp_m.group(1)

    # Паттерн: [AppRoutes.KEY]: { ... element: <CompName> }
    appRoutes_pattern = re.compile(
        r'\[AppRoutes\.(\w+)\][^:]*:\s*\{([^{}]*)\}', re.DOTALL
    )
    for m in appRoutes_pattern.finditer(content):
        key = m.group(1).lower()
        block = m.group(2)
        comp_m = re.search(r'element:\s*<(\w+)', block)
        if comp_m and key not in result:
            result[key] = comp_m.group(1)

    return result


def _resolve_to_file(repo: Path, config_dir: Path, module_path: str, alias_map: dict) -> Path | None:
    """
    Разрешает module_path в реальный .tsx/.jsx/.js файл.

    Alias-пути (@lab и т.п.) — пропускаем, они обрабатываются отдельно.
    Для прямых путей используем два паттерна:
      2a: путь файла без расширения заканчивается на module_path
          ("widgets/appoints/patient.appoints" -> patient.appoints.tsx)
      2b: родительская директория файла заканчивается на module_path
          ("pages/charts" -> pages/charts/charts.page.tsx)
    """
    for alias in alias_map:
        if module_path == alias or module_path.startswith(alias + '/'):
            return None

    extensions = ('.tsx', '.jsx', '.js')
    clean = module_path.lstrip('./')

    # Стратегия 1: прямой путь от известных корней
    for root in (repo, repo / 'src', repo / 'apps'):
        if not root.is_dir():
            continue
        for ext in extensions:
            p = root / (clean + ext)
            if p.exists():
                return p
        for ext in extensions:
            p = root / clean / ('index' + ext)
            if p.exists():
                return p

    # Стратегия 2: рекурсивный поиск
    clean_slash = '/' + clean
    suffix_parts = tuple(Path(clean).parts)

    for candidate in repo.rglob('*'):
        if 'node_modules' in candidate.parts:
            continue
        if not candidate.is_file() or candidate.suffix not in extensions:
            continue
        # Пропускаем тестовые файлы
        parts_lower = [p.lower() for p in candidate.parts]
        if 'test' in parts_lower or 'tests' in parts_lower or '__tests__' in parts_lower:
            continue
        cname = candidate.name.lower()
        if any(m in cname for m in ('.test.', '.spec.', '.test-utils.', '.stories.')):
            continue

        rel = candidate.relative_to(repo).as_posix()

        # 2a: путь файла без последнего расширения совпадает с module_path
        # "apps/crm/src/widgets/appoints/patient.appoints.tsx"
        # → rel_no_ext = "apps/crm/src/widgets/appoints/patient.appoints"
        # → ends with "widgets/appoints/patient.appoints" ✓
        rel_no_ext = rel.rsplit('.', 1)[0]
        if rel_no_ext == clean or rel_no_ext.endswith(clean_slash):
            return candidate

        # 2b: module_path является директорией-предком файла
        # "apps/crm/src/pages/charts/ui/charts.page/charts.page.tsx"
        # содержит "/apps/crm/src/pages/charts/" ✓
        rel_str = '/' + rel + '/'
        if ('/' + clean + '/') in rel_str:
            return candidate

    return None


def _find_barrel(repo: Path, barrel_rel: str) -> Path | None:
    """Ищет barrel index файл по относительному пути."""
    for ext in ('.ts', '.tsx', '.js'):
        p = repo / (barrel_rel + ext)
        if p.exists():
            return p
        p2 = repo / barrel_rel / ('index' + ext)
        if p2.exists():
            return p2
    return None


def resolve_barrel_component(repo: Path, alias_map: dict, module_path: str, comp_name: str) -> Path | None:
    """
    Для barrel-alias импортов: @lab -> apps/lab/src/index.ts -> lazy path -> file.
    Используется при наличии comp_name из router.config.
    """
    for alias, alias_target in alias_map.items():
        if module_path != alias and not module_path.startswith(alias + '/'):
            continue
        barrel_file = _find_barrel(repo, alias_target)
        if not barrel_file:
            return None
        barrel_content = barrel_file.read_text(encoding='utf-8', errors='ignore')

        # Паттерн: export const CompName = lazy(() => ... import('./path/to/file'))
        # или: export { CompName } from './path'
        lazy_pattern = re.compile(
            r'(?:export\s+const\s+' + re.escape(comp_name) + r'\s*=.*?import\(["\']([^"\']+)["\']\)' +
            r'|export\s*\{[^}]*\b' + re.escape(comp_name) + r'\b[^}]*\}\s*from\s*["\']([^"\']+)["\'])',
            re.DOTALL
        )
        m = lazy_pattern.search(barrel_content)
        if not m:
            return None
        rel_path = m.group(1) or m.group(2)

        # Путь относительно barrel файла
        barrel_dir = barrel_file.parent
        resolved_path = (barrel_dir / rel_path).resolve()
        for ext in ('.tsx', '.jsx', '.js'):
            p = Path(str(resolved_path) + ext)
            if p.exists():
                return p
            p2 = resolved_path / ('index' + ext)
            if p2.exists():
                return p2

    return None


def parse_router_config_full(repo_path: str) -> dict:
    """
    Расширенная версия: поддерживает и прямые пути, и barrel-aliases, и directory-aliases.
    Возвращает {route_key: Path}.
    """
    repo = Path(repo_path)
    result = {}

    config_files = _find_config_files(repo)
    if not config_files:
        return result

    alias_map = _read_tsconfig_aliases(repo)

    for config_file in config_files:
        content = config_file.read_text(encoding='utf-8', errors='ignore')
        import_map = _extract_imports(content)
        route_to_comp = _extract_route_entries(content)

        for route_key, comp_name in route_to_comp.items():
            if route_key in result:
                continue
            module_path = import_map.get(comp_name)
            if not module_path:
                continue

            resolved = _resolve_module(repo, config_file.parent, module_path, comp_name, alias_map)
            if resolved:
                result[route_key] = resolved

    return result


def _resolve_module(repo: Path, config_dir: Path, module_path: str, comp_name: str, alias_map: dict) -> Path | None:
    """
    Единая точка разрешения module_path -> file.
    Определяет тип алиаса (barrel vs directory) и применяет соответствующую стратегию.
    """
    # Находим подходящий алиас
    matched_alias = None
    matched_target = None
    for alias, target in alias_map.items():
        if module_path == alias or module_path.startswith(alias + '/'):
            matched_alias = alias
            matched_target = target
            break

    if matched_alias is None:
        # Нет алиаса — прямой путь
        return _resolve_to_file(repo, config_dir, module_path, {})

    # Есть алиас — проверяем тип
    barrel_file = _find_barrel(repo, matched_target)
    if barrel_file:
        # Barrel-alias (index.ts с lazy-exports): @lab, @main, etc.
        return resolve_barrel_component(repo, alias_map, module_path, comp_name)
    else:
        # Directory-alias (pages, widgets, etc.): подставляем реальный путь
        suffix = module_path[len(matched_alias):]  # "" или "/charts"
        resolved_path = matched_target + suffix    # "apps/crm/src/pages/charts"
        return _resolve_to_file(repo, config_dir, resolved_path, {})
