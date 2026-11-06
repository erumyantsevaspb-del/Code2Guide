"""
Рекурсивный обход импортов React-компонентов для сбора UI-элементов.

Поддерживает:
  - относительные импорты (./foo, ../bar)
  - directory-aliases из tsconfig (widgets/something → apps/crm/src/widgets/something)

НЕ следует:
  - barrel-aliases (@shared/ui, #crm-core/ui — импорты без sub-path)
  - сторонним библиотекам (@mui/..., react, react-dom, ...)
  - node_modules
"""

import re
from pathlib import Path

from core.services.ast_parser import parse_jsx_ast, _empty


_EXTENSIONS = ('.tsx', '.jsx', '.ts', '.js')

# Импорты без sub-path (точное совпадение с alias) пропускаем как barrel
# Сторонние пакеты (начинаются с @mui, react, и т.д.) пропускаем
_THIRD_PARTY_PREFIXES = (
    'react', 'react-dom', 'react-router', '@reduxjs', '@tanstack',
    '@mui', 'notistack', 'dayjs', 'clsx', '@emotion', 'axios',
    'lodash', 'zustand', 'mobx', 'immer', 'formik', 'yup', 'zod',
    'react-hook-form', 'react-query', 'react-use', 'framer-motion',
)


def collect_ui_from_component(
    file_path: str,
    repo_path: str,
    alias_map: dict | None = None,
    max_depth: int = 3,
    _visited: frozenset | None = None,
) -> dict:
    """
    Собирает UI-элементы из файла и его локальных дочерних компонентов.

    Args:
        file_path: путь к корневому файлу компонента
        repo_path: корень репозитория (для ограничения traversal)
        alias_map: маппинг алиасов tsconfig {alias: target_dir}
        max_depth: максимальная глубина рекурсии (0 = только текущий файл)
        _visited: внутренний параметр для отслеживания посещённых файлов

    Returns:
        объединённый dict от parse_jsx_ast со всех посещённых файлов
    """
    if alias_map is None:
        alias_map = {}
    if _visited is None:
        _visited = frozenset()

    abs_path = _safe_resolve(file_path)
    if abs_path is None or abs_path in _visited:
        return _empty()

    # Не выходим за пределы репо
    repo = Path(repo_path).resolve()
    try:
        abs_path.relative_to(repo)
    except ValueError:
        return _empty()

    _visited = _visited | {abs_path}

    result = parse_jsx_ast(str(abs_path))

    if max_depth <= 0:
        return result

    content = _read_file(abs_path)
    if not content:
        return result

    local_imports = _extract_imports(content)

    for imp_path in local_imports:
        resolved = _resolve_import(imp_path, abs_path.parent, repo, alias_map)
        if resolved is None:
            continue

        child = collect_ui_from_component(
            str(resolved), repo_path, alias_map, max_depth - 1, _visited
        )
        _merge(result, child)
        # Обновляем visited для следующих итераций этого цикла
        _visited = _visited | {resolved.resolve()}

    _deduplicate(result)
    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_resolve(path_str: str) -> Path | None:
    try:
        return Path(path_str).resolve()
    except Exception:
        return None


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''


def _extract_imports(content: str) -> list[str]:
    """Извлекает все import-пути из содержимого файла."""
    pattern = re.compile(r'''from\s+['"]([^'"]+)['"]''')
    return [m.group(1) for m in pattern.finditer(content)]


def _is_third_party(import_path: str) -> bool:
    """Возвращает True для сторонних библиотек."""
    for prefix in _THIRD_PARTY_PREFIXES:
        if import_path == prefix or import_path.startswith(prefix + '/') or import_path.startswith(prefix + '-'):
            return True
    # .css, .scss, .svg — не JS-модули
    if import_path.endswith(('.css', '.scss', '.svg', '.png', '.jpg', '.json')):
        return True
    return False


def _resolve_import(
    import_path: str,
    from_dir: Path,
    repo_root: Path,
    alias_map: dict,
) -> Path | None:
    """
    Разрешает строку импорта в реальный файл.

    Обрабатывает:
      1. Относительные пути: ./foo, ../bar/baz
      2. Directory-alias sub-path: widgets/something, lab/features/foo
    """
    if _is_third_party(import_path):
        return None

    # 1. Относительные импорты
    if import_path.startswith('./') or import_path.startswith('../'):
        base = (from_dir / import_path).resolve()
        return _find_file(base, repo_root)

    # 2. Directory-alias с sub-path (widgets/foo, lab/features/bar)
    #    Если import_path == alias точно → barrel/re-export, пропускаем
    for alias, target in alias_map.items():
        if import_path.startswith(alias + '/'):
            suffix = import_path[len(alias):]   # '/features/crown/color-crown'
            resolved_path = target + suffix      # 'apps/lab/src/features/crown/color-crown'
            base = (repo_root / resolved_path).resolve()
            result = _find_file(base, repo_root)
            if result:
                return result

    # 3. Иначе — пропускаем (third-party или barrel-exact)
    return None


def _is_test_file(path: Path) -> bool:
    """Возвращает True для тестовых файлов — их не следует использовать как компоненты."""
    parts_lower = [p.lower() for p in path.parts]
    if 'test' in parts_lower or 'tests' in parts_lower or '__tests__' in parts_lower:
        return True
    name = path.name.lower()
    for marker in ('.test.', '.spec.', '.test-utils.', '.stories.'):
        if marker in name:
            return True
    return False


def _find_file(base: Path, repo_root: Path) -> Path | None:
    """Ищет файл по базовому пути: пробует расширения и index."""
    # Проверяем что в пределах репо
    try:
        base.relative_to(repo_root)
    except ValueError:
        return None

    # node_modules: пропускаем
    if 'node_modules' in base.parts:
        return None

    for ext in _EXTENSIONS:
        p = Path(str(base) + ext)
        if p.exists() and not _is_test_file(p):
            return p

    for ext in _EXTENSIONS:
        p = base / ('index' + ext)
        if p.exists() and not _is_test_file(p):
            return p

    return None


def _merge(target: dict, source: dict) -> None:
    """Добавляет элементы из source в target без дубликатов."""
    target_field_labels = {f.get('label', '').lower() for f in target['fields']}
    for f in source.get('fields', []):
        label = f.get('label', '').lower()
        if label and label not in target_field_labels:
            target['fields'].append(f)
            target_field_labels.add(label)

    target_buttons = {b.lower() for b in target['buttons']}
    for b in source.get('buttons', []):
        if b and b.lower() not in target_buttons:
            target['buttons'].append(b)
            target_buttons.add(b.lower())

    target_columns = {c.lower() for c in target['columns']}
    for c in source.get('columns', []):
        if c and c.lower() not in target_columns:
            target['columns'].append(c)
            target_columns.add(c.lower())

    if not target.get('title') and source.get('title'):
        target['title'] = source['title']


def _deduplicate(result: dict) -> None:
    """Дедуплицирует все коллекции на месте."""
    seen_labels = set()
    deduped_fields = []
    for f in result['fields']:
        key = f.get('label', '').lower()
        if key and key not in seen_labels:
            seen_labels.add(key)
            deduped_fields.append(f)
    result['fields'] = deduped_fields

    result['buttons'] = list(dict.fromkeys(result['buttons']))
    result['columns'] = list(dict.fromkeys(result['columns']))
