import re
from pathlib import Path

_ROUTE_NAME_RU = {
    'home': 'Главная', 'dashboard': 'Дашборд', 'profile': 'Профиль',
    'settings': 'Настройки', 'login': 'Вход', 'register': 'Регистрация',
    'patients': 'Пациенты', 'appointments': 'Приёмы', 'appoints': 'Приёмы',
    'claims': 'Заявки', 'tickets': 'Заявки', 'consumables': 'Расходники',
    'materials': 'Материалы', 'reports': 'Отчёты', 'statements': 'Ведомости',
    'contacts': 'Контакты', 'companies': 'Компании', 'deals': 'Сделки',
    'orders': 'Заказы', 'products': 'Товары', 'users': 'Пользователи',
    'tasks': 'Задачи', 'calendar': 'Календарь', 'analytics': 'Аналитика',
    'invoices': 'Счета', 'documents': 'Документы', 'files': 'Файлы',
    'notifications': 'Уведомления', 'messages': 'Сообщения',
    'shift': 'Смена', 'duty schedule': 'График дежурств',
    'managment': 'Управление', 'connectors': 'Интеграции',
    'changelog': 'Журнал изменений', 'research list': 'Список исследований',
    'extra': 'Доп. услуги', 'extra claims': 'Заявки по доп. услугам',
    'image reports': 'Отчёты по снимкам', 'partners': 'Партнёры',
}

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


def parse_routepath_routes(source_path):
    """
    Читает маршруты из RoutePath объекта в TypeScript (router.ts / routes.ts).
    Формат: export const RoutePath: Record<...> = { key: "/path", ... }
    """
    source = Path(source_path)
    routes = []

    # Ищем файлы-кандидаты
    candidates = []
    for ext in ('*.ts', '*.tsx'):
        for f in source.rglob(ext):
            if 'node_modules' in f.parts:
                continue
            if f.name.lower() in ('router.ts', 'routes.ts', 'router.tsx', 'routes.tsx'):
                candidates.append(f)

    for filepath in candidates:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        if 'RoutePath' not in content and 'routePath' not in content:
            continue

        # Ищем блок RoutePath = { ... }
        block_match = re.search(
            r'(?:RoutePath|routePath)\s*[=:][^{]*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
            content, re.DOTALL
        )
        if not block_match:
            continue

        block = block_match.group(1)
        pairs = re.findall(r'(\w+)\s*:\s*["\']([^"\']+)["\']', block)

        # Фильтруем дубли путей и служебные роуты
        seen_paths = set()
        skip_keys = {'forbidden', 'not_found', 'technical_works', 'storybook', 'print_agreement'}

        for key, path in pairs:
            if key in skip_keys:
                continue
            if path in seen_paths:
                continue
            # Пропускаем sub-роуты (create, edit, view и т.п.)
            sub_keywords = ('create', 'edit', 'view', 'history', 'search', 'record', 'card')
            parts = key.split('_')
            if any(p in sub_keywords for p in parts[1:]):
                continue
            seen_paths.add(path)
            raw_name = key.replace('_', ' ')
            name = _ROUTE_NAME_RU.get(raw_name.lower(), raw_name.title())
            routes.append({'path': path, 'name': name, 'component': key})

        if routes:
            return routes

    return routes


def parse_nextjs_routes(source_path):
    """
    Читает маршруты из Next.js App Router — папки с page.tsx/page.jsx.
    """
    source = Path(source_path)
    routes = []

    # Ищем папку app/
    app_dirs = list(source.rglob('app'))
    app_dirs = [d for d in app_dirs if d.is_dir() and 'node_modules' not in d.parts]
    if not app_dirs:
        return routes

    app_dir = min(app_dirs, key=lambda p: len(p.parts))

    for page_file in app_dir.rglob('page.tsx'):
        rel = page_file.parent.relative_to(app_dir)
        parts = rel.parts

        # Пропускаем служебные сегменты Next.js
        clean_parts = []
        for p in parts:
            if p.startswith('(') and p.endswith(')'):
                continue  # группировка: (routes), (auth) и т.д.
            if p.startswith('[') and p.endswith(']'):
                continue  # динамические сегменты: [locale], [id]
            clean_parts.append(p)

        if not clean_parts:
            route_path = '/'
            name = 'Главная'
        else:
            route_path = '/' + '/'.join(clean_parts)
            raw_name = clean_parts[-1].replace('-', ' ').replace('_', ' ')
            name = _ROUTE_NAME_RU.get(raw_name.lower(), raw_name.title())

        routes.append({
            'path': route_path,
            'name': name,
            'component': ''.join(p.title() for p in clean_parts) or 'Home',
        })

    return routes


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