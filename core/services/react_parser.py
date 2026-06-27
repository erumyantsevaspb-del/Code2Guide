import re
from pathlib import Path

# Человекочитаемые названия для resource-имён react-admin
_RESOURCE_LABELS = {
    'contacts': 'Контакты',
    'companies': 'Компании',
    'deals': 'Сделки',
    'sales': 'Продажи',
    'tasks': 'Задачи',
    'tags': 'Теги',
    'users': 'Пользователи',
    'orders': 'Заказы',
    'products': 'Товары',
    'categories': 'Категории',
    'invoices': 'Счета',
    'customers': 'Клиенты',
    'notes': 'Заметки',
    'settings': 'Настройки',
    'dashboard': 'Дашборд',
}


def parse_react_admin_routes(source_path):
    """
    Ищет <Resource name="..."> в TSX/JSX файлах проекта.
    Возвращает список маршрутов в том же формате что parse_routes().
    """
    source = Path(source_path)
    routes = []
    seen = set()

    for ext in ('*.tsx', '*.jsx', '*.ts', '*.js'):
        for filepath in source.rglob(ext):
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            if '<Resource' not in content:
                continue
            names = re.findall(r'<Resource[^>]+name=["\']([^"\']+)["\']', content)
            for name in names:
                if name in seen:
                    continue
                seen.add(name)
                label = _RESOURCE_LABELS.get(name, name.replace('_', ' ').title())
                routes.append({
                    'path': f'/{name}',
                    'name': label,
                    'component': name,
                })

    return routes


def parse_component_imports(routes_path):
    """
    Извлекает соответствие:
    компонент -> путь к файлу
    """

    with open(routes_path, encoding="utf-8") as f:
        content = f.read()

    imports = {}

    pattern = (
        r'const\s+(\w+)\s*='
        r'\s*React\.lazy\(\(\)\s*=>\s*import\('
        r"['\"](.+?)['\"]"
    )

    matches = re.findall(
        pattern,
        content
    )

    for component, path in matches:
        imports[component] = path

    return imports

def parse_routes(file_path):
    """
    Извлекает маршруты из routes.js
    """

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    routes = []

    pattern = (
        r"\{\s*path:\s*'([^']+)'.*?"
        r"name:\s*'([^']+)'.*?"
        r"element:\s*(\w+)"
    )

    matches = re.findall(
        pattern,
        content,
        re.DOTALL
    )

    for path, name, component in matches:
        routes.append({
            "path": path,
            "name": name,
            "component": component,
        })

    return routes