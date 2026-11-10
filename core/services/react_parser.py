import re
from pathlib import Path

# Словарь точных совпадений (полные названия роутов)
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
    'duty': 'График дежурств', 'salary': 'Зарплата', 'wagework': 'Зарплата',
    'support': 'Поддержка', 'research': 'Исследования',
}

# Словарь отдельных слов для пословного перевода составных роутов
_WORD_RU = {
    'home': 'Главная', 'dashboard': 'Дашборд', 'profile': 'Профиль',
    'settings': 'Настройки', 'login': 'Вход', 'register': 'Регистрация',
    'patients': 'Пациенты', 'patient': 'Пациент',
    'appointments': 'Приёмы', 'appoints': 'Приёмы', 'appointment': 'Приём',
    'claims': 'Заявки', 'claim': 'Заявка',
    'tickets': 'Заявки', 'ticket': 'Заявка',
    'consumables': 'Расходники', 'consumable': 'Расходник',
    'consumption': 'Списание', 'expense': 'Расход', 'receipt': 'Приход',
    'materials': 'Материалы', 'material': 'Материал',
    'reports': 'Отчёты', 'report': 'Отчёт',
    'statements': 'Ведомости', 'statement': 'Ведомость',
    'contacts': 'Контакты', 'contact': 'Контакт',
    'companies': 'Компании', 'company': 'Компания',
    'deals': 'Сделки', 'deal': 'Сделка',
    'orders': 'Заказы', 'order': 'Заказ',
    'products': 'Товары', 'product': 'Товар',
    'users': 'Пользователи', 'user': 'Пользователь',
    'tasks': 'Задачи', 'task': 'Задача',
    'calendar': 'Календарь', 'analytics': 'Аналитика',
    'invoices': 'Счета', 'invoice': 'Счёт',
    'documents': 'Документы', 'document': 'Документ',
    'files': 'Файлы', 'file': 'Файл',
    'notifications': 'Уведомления', 'messages': 'Сообщения',
    'shift': 'Смена', 'duty': 'Дежурство', 'schedule': 'График',
    'management': 'Управление', 'managment': 'Управление',
    'connectors': 'Интеграции', 'connector': 'Интеграция',
    'changelog': 'Журнал изменений', 'extra': 'Доп. услуги',
    'partners': 'Партнёры', 'partner': 'Партнёр',
    'support': 'Поддержка', 'research': 'Исследование',
    'list': 'Список', 'image': 'Снимки', 'images': 'Снимки',
    'association': 'Прикрепление', 'registration': 'Регистрация',
    'salary': 'Зарплата', 'wagework': 'Зарплата',
    'dc': 'ДЦ', 'sc': 'СЦ', 'lk': 'ЛК',
    'tech': 'Техн.', 'info': 'Инфо',
    'create': 'Создание', 'edit': 'Редактирование', 'view': 'Просмотр',
    'history': 'История',
}


def _translate_route_name(raw_name: str) -> str:
    """Переводит название роута: сначала точное совпадение, затем пословно."""
    key = raw_name.lower().strip()
    if key in _ROUTE_NAME_RU:
        return _ROUTE_NAME_RU[key]
    # Пословный перевод
    words = key.split()
    translated = [_WORD_RU.get(w, w.upper() if len(w) <= 3 else w.title()) for w in words]
    return ' '.join(translated)

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
        # Computed keys: [AppRoutes.MAIN]: '/path' — используем последний сегмент ключа
        for computed_key, path in re.findall(r'\[(\w+(?:\.\w+)*)\]\s*:\s*["\']([^"\']+)["\']', block):
            key_name = computed_key.split('.')[-1].lower()
            pairs.append((key_name, path))

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
            name = _translate_route_name(raw_name)
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

    seen_paths = set()
    for page_file in sorted(app_dir.rglob('page.*')):
        if page_file.suffix not in ('.tsx', '.jsx', '.ts', '.js'):
            continue
        rel = page_file.parent.relative_to(app_dir)
        parts = rel.parts

        has_dynamic = False
        clean_parts = []
        for p in parts:
            if p.startswith('(') and p.endswith(')'):
                continue  # группировка: (routes), (auth) и т.д.
            if p.startswith('[') and p.endswith(']'):
                has_dynamic = True
                clean_parts.append(p)  # сохраняем как есть: [id]
            else:
                clean_parts.append(p)

        if not clean_parts:
            route_path = '/'
            name = 'Главная'
        else:
            route_path = '/' + '/'.join(clean_parts)
            # Имя берём из последнего статического сегмента
            static_parts = [p for p in clean_parts if not (p.startswith('[') and p.endswith(']'))]
            label = (static_parts[-1] if static_parts else clean_parts[-1])
            raw_name = label.replace('-', ' ').replace('_', ' ')
            name = _translate_route_name(raw_name)

        if route_path in seen_paths:
            continue
        seen_paths.add(route_path)

        routes.append({
            'path': route_path,
            'name': name,
            'component': ''.join(
                p.strip('[]').title() for p in clean_parts
            ) or 'Home',
            # Скриншот динамической страницы без параметра сделать нельзя
            '_dynamic': has_dynamic,
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

def parse_jsx_routes(source_path):
    """
    Парсит маршруты React Router v6 из JSX/TSX файлов.

    Поддерживает:
    - <Route path="..." element={<Component />} />        — плоский формат
    - <Route path="..." element={<Component />}>          — родительский маршрут с детьми
    - <Route index element={<Component />} />             — index-маршрут (путь = путь родителя)
    - Вложенные <Route> с восстановлением абсолютного пути
    - Фильтрацию Layout/Wrapper/Guard компонентов
    """
    source = Path(source_path)
    routes = []

    # Ключевые слова компонентов-оболочек — не являются самостоятельными экранами
    _LAYOUT_KEYWORDS = (
        'layout', 'wrapper', 'guard', 'provider', 'outlet',
        'protected', 'private', 'auth', 'shell', 'frame',
    )

    def _is_layout_component(name: str) -> bool:
        low = name.lower()
        return any(kw in low for kw in _LAYOUT_KEYWORDS)

    def _normalize_path(parent: str, child: str) -> str:
        """Собирает абсолютный путь из родительского и дочернего."""
        if child.startswith('/'):
            return child
        parent = parent.rstrip('/')
        if not child:
            return parent or '/'
        return (parent + '/' + child) if parent else '/' + child

    def _parse_file(content: str) -> list:
        """
        Возвращает список {'path', 'name', 'component'} из одного файла.
        Разбирает теги <Route ...> построчно с учётом вложенности.
        """
        file_routes = []

        # Извлекаем все <Route ...> теги (включая многострочные)
        # Паттерн захватывает открывающий тег Route с его атрибутами
        route_tag_re = re.compile(
            r'<Route\b([^>]*?)(?:/>|>)',
            re.DOTALL,
        )

        path_re = re.compile(r'''path\s*=\s*["']([^"']+)["']''')
        # element={<Component />} — React Router v6; component={Component} — v4/v5
        element_re = re.compile(r'(?:element\s*=\s*\{<(\w+)|component\s*=\s*\{(\w+))')
        index_re = re.compile(r'\bindex\b')

        # Собираем все совпадения с позицией в файле
        tags = []
        for m in route_tag_re.finditer(content):
            attrs = m.group(1)
            path_m = path_re.search(attrs)
            elem_m = element_re.search(attrs)
            is_index = bool(index_re.search(attrs))
            is_self_closing = m.group(0).endswith('/>')

            path_val = path_m.group(1) if path_m else None
            # group(1) = element={<X}, group(2) = component={X}
            component = (elem_m.group(1) or elem_m.group(2)) if elem_m else None
            tags.append({
                'pos': m.start(),
                'end': m.end(),
                'path': path_val,
                'component': component,
                'is_index': is_index,
                'self_closing': is_self_closing,
            })

        if not tags:
            return file_routes

        # Простая эвристика для восстановления вложенности:
        # Находим закрывающие теги </Route> чтобы определить родителей
        close_re = re.compile(r'</Route\s*>')
        close_positions = [m.start() for m in close_re.finditer(content)]

        # Строим дерево: для каждого открывающего тега определяем родителя
        # через позиции (тег является потомком ближайшего незакрытого родителя)
        stack = []  # [(path_val, component)]

        # Обрабатываем теги в порядке появления
        # Используем упрощённый подход: смотрим на отступы строк
        lines = content.splitlines()
        line_starts = []
        pos = 0
        for line in lines:
            line_starts.append(pos)
            pos += len(line) + 1  # +1 для \n

        def _line_indent(char_pos: int) -> int:
            for i in range(len(line_starts) - 1, -1, -1):
                if line_starts[i] <= char_pos:
                    return len(lines[i]) - len(lines[i].lstrip())
            return 0

        # Восстанавливаем иерархию через стек пути по отступам
        indent_stack = []  # [(indent_level, abs_path)]

        for tag in tags:
            indent = _line_indent(tag['pos'])

            # Очищаем стек: убираем родителей с таким же или большим отступом
            while indent_stack and indent_stack[-1][0] >= indent:
                indent_stack.pop()

            parent_path = indent_stack[-1][1] if indent_stack else ''

            if tag['is_index']:
                abs_path = parent_path or '/'
            elif tag['path']:
                abs_path = _normalize_path(parent_path, tag['path'])
            else:
                abs_path = None

            component = tag['component']

            # Если не self-closing — это родительский маршрут, добавляем в стек
            if not tag['self_closing'] and abs_path is not None:
                indent_stack.append((indent, abs_path))

            if abs_path and component:
                file_routes.append({
                    'path': abs_path,
                    'component': component,
                })

        return file_routes

    # Ищем файлы с маршрутами React Router v6
    candidates = []
    for ext in ('*.jsx', '*.tsx', '*.js', '*.ts'):
        for f in source.rglob(ext):
            if 'node_modules' in f.parts:
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            # Файлы с импортом из react-router или react-router-dom и тегами Route
            if 'react-router' in content and '<Route' in content:
                candidates.append((f, content))

    if not candidates:
        return routes

    # Берём файл с наибольшим количеством <Route тегов (обычно App.jsx)
    candidates.sort(key=lambda x: x[1].count('<Route'), reverse=True)
    _, content = candidates[0]

    raw = _parse_file(content)

    # Фильтруем и дедуплицируем
    seen_paths = set()
    skip_path_segments = (':',  '*')  # динамические и catch-all

    for item in raw:
        path = item['path']
        component = item['component']

        # Пропускаем Layout-компоненты
        if _is_layout_component(component):
            continue

        # Пропускаем динамические сегменты (:id, *, :slug)
        if any(seg.startswith(':') or seg == '*' for seg in path.split('/')):
            continue

        if path in seen_paths:
            continue

        seen_paths.add(path)
        raw_name = component
        # Убираем суффиксы Page/View/Screen для перевода
        for suffix in ('Page', 'View', 'Screen'):
            if raw_name.endswith(suffix) and len(raw_name) > len(suffix):
                raw_name = raw_name[:-len(suffix)]
                break

        # CamelCase → слова
        words = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw_name)
        name = _translate_route_name(words.lower())

        routes.append({
            'path': path,
            'name': name,
            'component': component,
        })

    return routes


def parse_browser_router_routes(source_path):
    """
    Парсит маршруты из createBrowserRouter([...]) — объектный массив React Router v6/v7.

    Поддерживает:
    - Инлайн-массив: createBrowserRouter([{ path: "...", Component: Comp }, ...])
    - Переменная: const routes = [...]; createBrowserRouter(routes)
    - Поле Component (React Router v7) и element: <Comp /> (v6)
    - Импорт из "react-router" и "react-router-dom"

    Ограничения:
    - Вложенные children не раскрываются: только объекты первого уровня массива
    - element с выражением (не компонентом) не распознаётся, например element: renderPage()
    - Объявление маршрутов через функцию-фабрику не поддерживается
    """
    source = Path(source_path)

    _LAYOUT_KEYWORDS = (
        'layout', 'wrapper', 'guard', 'provider', 'outlet',
        'protected', 'private', 'auth', 'shell', 'frame',
    )

    def _is_layout_component(name: str) -> bool:
        low = name.lower()
        return any(kw in low for kw in _LAYOUT_KEYWORDS)

    def _extract_array_block(content: str) -> str | None:
        """Извлекает содержимое массива маршрутов из createBrowserRouter."""
        # Случай 1: инлайн-массив createBrowserRouter([...])
        inline_re = re.compile(r'createBrowserRouter\s*\(\s*\[')
        m = inline_re.search(content)
        if m:
            start = content.index('[', m.start())
            depth = 0
            for j in range(start, len(content)):
                if content[j] == '[':
                    depth += 1
                elif content[j] == ']':
                    depth -= 1
                    if depth == 0:
                        return content[start + 1:j]
            return None

        # Случай 2: переменная createBrowserRouter(routesVar)
        var_re = re.compile(r'createBrowserRouter\s*\(\s*(\w+)\s*\)')
        vm = var_re.search(content)
        if vm:
            varname = vm.group(1)
            arr_re = re.compile(
                rf'(?:const|let|var)\s+{re.escape(varname)}\s*(?::[^=]*)?\s*=\s*\['
            )
            am = arr_re.search(content)
            if am:
                start = content.index('[', am.end() - 1)
                depth = 0
                for j in range(start, len(content)):
                    if content[j] == '[':
                        depth += 1
                    elif content[j] == ']':
                        depth -= 1
                        if depth == 0:
                            return content[start + 1:j]
        return None

    def _parse_top_level_objects(block: str) -> list:
        """Разбирает объекты первого уровня массива (не вложенные children)."""
        objects = []
        depth = 0
        obj_start = None
        for k, ch in enumerate(block):
            if ch == '{':
                if depth == 0:
                    obj_start = k
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and obj_start is not None:
                    objects.append(block[obj_start:k + 1])
                    obj_start = None
        return objects

    path_re = re.compile(r'''path\s*:\s*["']([^"']+)["']''')
    component_re = re.compile(r'''(?:Component|element)\s*:\s*(?:<\s*)?(\w+)''')

    routes = []
    seen_paths = set()

    for ext in ('*.tsx', '*.ts', '*.jsx', '*.js'):
        for filepath in source.rglob(ext):
            if 'node_modules' in filepath.parts:
                continue
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            if 'createBrowserRouter' not in content:
                continue
            # Проверяем импорт именно из пакетов react-router или react-router-dom,
            # а не из локального модуля с похожим именем (./custom-router и т.п.)
            if not re.search(r'''from\s+["']react-router(?:-dom)?["']''', content):
                continue

            block = _extract_array_block(content)
            if not block:
                continue

            for obj in _parse_top_level_objects(block):
                pm = path_re.search(obj)
                cm = component_re.search(obj)
                if not pm or not cm:
                    continue

                path_val = pm.group(1)
                component = cm.group(1)

                # Пропускаем catch-all и динамические параметры
                if path_val == '*' or any(
                    seg.startswith(':') or seg == '*'
                    for seg in path_val.split('/')
                ):
                    continue

                # Пропускаем Layout/Guard компоненты
                if _is_layout_component(component):
                    continue

                if path_val in seen_paths:
                    continue
                seen_paths.add(path_val)

                raw_name = component
                for suffix in ('Page', 'View', 'Screen'):
                    if raw_name.endswith(suffix) and len(raw_name) > len(suffix):
                        raw_name = raw_name[:-len(suffix)]
                        break
                words = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw_name)
                name = _translate_route_name(words.lower())

                routes.append({'path': path_val, 'name': name, 'component': component})

            if routes:
                return routes

    return routes


def parse_nextjs_pages_routes(source_path):
    """
    Читает маршруты из Next.js Pages Router — папки pages/.
    Исключает _app, _document, _error, api/ и динамические сегменты [id].
    """
    source = Path(source_path)
    routes = []
    seen_paths = set()

    pages_dirs = [d for d in source.rglob('pages') if d.is_dir() and 'node_modules' not in d.parts]
    if not pages_dirs:
        return routes

    pages_dir = min(pages_dirs, key=lambda p: len(p.parts))

    for page_file in pages_dir.rglob('*'):
        if not page_file.is_file():
            continue
        if page_file.suffix not in ('.tsx', '.jsx', '.ts', '.js'):
            continue

        rel = page_file.relative_to(pages_dir)
        parts = list(rel.parts)

        # Исключаем служебные файлы и API
        if parts[0].startswith('_') or parts[0] == 'api':
            continue

        # Убираем расширение из последнего сегмента
        stem = parts[-1].rsplit('.', 1)[0]
        if stem.startswith('_'):
            continue

        path_parts = parts[:-1]
        if stem != 'index':
            path_parts.append(stem)

        # Исключаем динамические сегменты [id]
        if any(p.startswith('[') and p.endswith(']') for p in path_parts):
            continue

        route_path = '/' + '/'.join(path_parts) if path_parts else '/'

        if route_path in seen_paths:
            continue
        seen_paths.add(route_path)

        raw_name = (path_parts[-1] if path_parts else 'home').replace('-', ' ').replace('_', ' ')
        name = _translate_route_name(raw_name)
        component = ''.join(p.title() for p in path_parts) or 'Home'

        routes.append({'path': route_path, 'name': name, 'component': component})

    return routes


def parse_distributed_router_files(source_path):
    """
    Парсит маршруты из распределённых файлов вида *.router.tsx / *.router.ts.

    Применяется в проектах, где роуты разбиты по файлам-модулям, например:
      src/views/dashboard/dashboard.router.tsx → path: 'dashboard'
      src/views/auth/auth.router.tsx → path: 'auth/login'

    Ограничения:
    - Извлекаются только строковые литералы path; динамические сегменты пропускаются
    - Дочерние пути без ведущего / нормализуются с ведущим слэшем
    """
    source = Path(source_path)
    routes = []
    seen_paths = set()

    path_re = re.compile(r'''path\s*:\s*["']([^"']+)["']''')
    component_re = re.compile(r'''(?:Component|element)\s*:\s*(?:<\s*)?(\w+)''')

    for ext in ('*.router.tsx', '*.router.ts', '*.router.jsx', '*.router.js'):
        for filepath in sorted(source.rglob(ext)):
            if 'node_modules' in filepath.parts:
                continue
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            for pm in path_re.finditer(content):
                path_val = pm.group(1)
                if path_val in seen_paths:
                    continue
                if path_val == '*' or any(
                    seg.startswith(':') or seg == '*'
                    for seg in path_val.split('/')
                ):
                    continue

                seen_paths.add(path_val)
                normalized = '/' + path_val.lstrip('/')

                last_seg = path_val.rstrip('/').split('/')[-1]
                name = _translate_route_name(last_seg.replace('-', ' ').replace('_', ' '))

                cm = component_re.search(content)
                component = cm.group(1) if cm else last_seg

                routes.append({'path': normalized, 'name': name, 'component': component})

    return routes


def parse_paths_config_routes(source_path):
    """
    Парсит маршруты из файлов конфигурации путей — paths.ts, paths.js и аналогов.

    Применяется в monorepo-проектах (например, Bulletproof React), где маршруты
    задаются константами вида:
      export const paths = { home: { path: '/' }, app: { dashboard: { path: '' } } }

    Алгоритм:
    1. Ищет файлы с именем paths.ts / paths.js / routes-config.ts и т.п.
    2. Извлекает все строки вида `path: 'value'`
    3. Пропускает пустые пути, catch-all и динамические сегменты

    Ограничения:
    - Не разрешает вложенные ссылки; только строковые литералы
    - Имя маршрута выводится из последнего сегмента пути
    """
    source = Path(source_path)
    routes = []
    seen_paths = set()

    _PATH_FILE_KEYWORDS = ('paths', 'routes-config', 'route-config', 'routeconfig', 'navigation')

    path_val_re = re.compile(r'''path\s*:\s*["']([^"']*)["']''')

    candidates = []
    for ext in ('*.ts', '*.js', '*.tsx'):
        for filepath in source.rglob(ext):
            if 'node_modules' in filepath.parts:
                continue
            stem = filepath.stem.lower()
            if any(kw in stem for kw in _PATH_FILE_KEYWORDS):
                candidates.append(filepath)

    for filepath in sorted(candidates):
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        # Должен содержать несколько path: определений — не роутер, а конфиг
        path_matches = list(path_val_re.finditer(content))
        if len(path_matches) < 2:
            continue

        for pm in path_matches:
            path_val = pm.group(1)
            if not path_val:
                continue
            if path_val in seen_paths:
                continue
            if path_val == '*' or any(
                seg.startswith(':') or seg == '*'
                for seg in path_val.split('/')
            ):
                continue

            seen_paths.add(path_val)
            normalized = '/' + path_val.lstrip('/') if path_val else '/'

            last_seg = normalized.rstrip('/').split('/')[-1] or 'home'
            name = _translate_route_name(last_seg.replace('-', ' ').replace('_', ' '))

            routes.append({'path': normalized, 'name': name, 'component': last_seg})

    return routes


def parse_remix_flat_routes(source_path):
    """
    Парсит маршруты из структуры файловой системы в стиле remix-flat-routes.

    Применяется в проектах на React Router v7 / Remix, где маршруты определяются
    именованием файлов, а не кодом:
      app/routes/_auth.login.tsx  → /login
      app/routes/dashboard.tsx    → /dashboard
      app/routes/organizations_+/$orgSlug+/dashboard.tsx → /organizations/:orgSlug/dashboard

    Соглашения:
    - Сегмент начинается с `_имя.` → layout route, не добавляется в URL
    - Суффикс `+` у каталога → pathless layout group
    - `$param` → `:param` (динамический сегмент)
    - Точка `.` разделяет сегменты URL внутри имени файла
    - `_index` → index route (пустой путь)

    Ограничения:
    - Динамические сегменты `:param` пропускаются в результате
    - Не разворачивает children (каждый лист файловой системы — отдельный маршрут)
    """
    source = Path(source_path)

    routes_dirs = []
    for candidate in (source / 'app' / 'routes', source / 'src' / 'routes'):
        if candidate.is_dir():
            routes_dirs.append(candidate)

    if not routes_dirs:
        return []

    routes = []
    seen_paths = set()

    def _convert_segment(seg: str) -> str | None:
        """Конвертирует сегмент remix-flat-routes в URL-часть. None = пропустить."""
        # Убираем суффикс +
        seg = seg.rstrip('+').rstrip('_')
        # Layout-prefix: _name. → пропускаем этот сегмент
        if seg.startswith('_'):
            return None
        # Динамический параметр
        if seg.startswith('$'):
            return ':' + seg[1:]
        return seg

    def _file_to_path(filepath: Path, routes_dir: Path) -> str | None:
        """Конвертирует путь к файлу в URL-путь по правилам remix-flat-routes."""
        rel = filepath.relative_to(routes_dir)
        parts = list(rel.parts)

        # Убираем расширение из последнего элемента
        parts[-1] = parts[-1].rsplit('.', 1)[0]

        url_segments = []
        for part in parts:
            # Разбиваем по точке (flat-routes convention: a.b.c → a/b/c)
            sub_segs = part.split('.')
            for seg in sub_segs:
                converted = _convert_segment(seg)
                if converted is None:
                    continue
                if converted == '_index' or converted == 'index':
                    continue  # index route — не добавляем сегмент
                # spec-файлы рядом с роутами (co-located tests) — пропускаем
                if converted == 'spec':
                    return None
                url_segments.append(converted)

        return '/' + '/'.join(url_segments) if url_segments else '/'

    for routes_dir in routes_dirs:
        for filepath in sorted(routes_dir.rglob('*')):
            if not filepath.is_file():
                continue
            if filepath.suffix not in ('.tsx', '.jsx', '.ts', '.js'):
                continue
            if 'node_modules' in filepath.parts:
                continue

            url_path = _file_to_path(filepath, routes_dir)
            if url_path is None:
                continue

            # Пропускаем динамические, catch-all и API-роуты
            if any(seg.startswith(':') or seg == '*' for seg in url_path.split('/')):
                continue
            if url_path.startswith('/api/'):
                continue

            if url_path in seen_paths:
                continue
            seen_paths.add(url_path)

            last_seg = url_path.rstrip('/').split('/')[-1] or 'home'
            name = _translate_route_name(last_seg.replace('-', ' ').replace('_', ' '))
            stem = filepath.stem.split('.')[0]

            routes.append({'path': url_path, 'name': name, 'component': stem})

    return routes


def parse_component_pages_fallback(source_path):
    """
    Эвристический фолбэк: ищет компоненты-страницы в src/pages/, src/views/, src/screens/.
    Возвращает приблизительные маршруты, помеченные флагом approximate=True.
    Использовать только если все остальные парсеры вернули пустой список.
    """
    source = Path(source_path)
    routes = []
    seen_paths = set()

    # Директории, где обычно лежат страницы
    page_dirs = []
    for candidate in ('pages', 'views', 'screens'):
        d = source / 'src' / candidate
        if d.is_dir():
            page_dirs.append(d)

    if not page_dirs:
        return routes

    _SKIP_NAMES = {
        'index', 'app', 'main', 'root', 'layout', 'template',
        'notfound', 'not-found', 'error', '404', '500',
    }

    for page_dir in page_dirs:
        for page_file in sorted(page_dir.rglob('*')):
            if not page_file.is_file():
                continue
            if page_file.suffix not in ('.tsx', '.jsx'):
                continue

            stem = page_file.stem
            stem_lower = stem.lower()

            # Убираем суффикс Page/View/Screen
            clean = stem_lower
            for suffix in ('page', 'view', 'screen'):
                if clean.endswith(suffix) and len(clean) > len(suffix):
                    clean = clean[:-len(suffix)]
                    break

            if clean in _SKIP_NAMES:
                continue

            route_path = '/' + clean.replace('_', '-')
            if route_path in seen_paths:
                continue
            seen_paths.add(route_path)

            name = _translate_route_name(clean.replace('-', ' ').replace('_', ' '))
            routes.append({
                'path': route_path,
                'name': name,
                'component': stem,
                'approximate': True,
            })

    return routes


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