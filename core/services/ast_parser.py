"""
AST-парсер JSX/TSX файлов на основе tree-sitter.
Извлекает UI-элементы: поля, кнопки, колонки таблиц, заголовки.
"""
from pathlib import Path


def parse_jsx_ast(file_path: str) -> dict:
    """
    Парсит JSX/TSX файл через tree-sitter.
    Возвращает:
    {
      'fields': [{'label': '...', 'placeholder': '...', 'type': 'text'}],
      'buttons': ['Сохранить', 'Отмена'],
      'columns': ['Номер заявки', 'Дата', 'Статус'],
      'selects': [{'label': '...', 'options': [...]}],
      'title': '...',
    }
    """
    try:
        content = Path(file_path).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return _empty()

    try:
        tree = _parse(content, file_path)
        if tree is None:
            return _empty()
        return _extract(tree.root_node, content)
    except Exception as e:
        print(f"AST parse error {file_path}: {e}")
        return _empty()


def parse_jsx_content(content: str, is_tsx: bool = True) -> dict:
    """Парсит JSX/TSX из строки."""
    try:
        tree = _parse_content(content, is_tsx)
        if tree is None:
            return _empty()
        return _extract(tree.root_node, content)
    except Exception as e:
        print(f"AST parse error: {e}")
        return _empty()


# ── внутренние функции ──────────────────────────────────────────────

def _parse(content: str, file_path: str):
    is_tsx = file_path.endswith(('.tsx', '.ts'))
    return _parse_content(content, is_tsx)


def _parse_content(content: str, is_tsx: bool = True):
    try:
        if is_tsx:
            import tree_sitter_typescript as tsts
            from tree_sitter import Language, Parser
            lang = Language(tsts.language_tsx())
        else:
            import tree_sitter_javascript as tsjs
            from tree_sitter import Language, Parser
            lang = Language(tsjs.language())

        parser = Parser(lang)
        return parser.parse(content.encode('utf-8', errors='replace'))
    except Exception as e:
        print(f"tree-sitter init error: {e}")
        return None


def _extract(root, source: str) -> dict:
    result = _empty()
    src = source.encode('utf-8', errors='replace')

    _walk(root, src, result)

    # Дедупликация
    result['buttons'] = list(dict.fromkeys(b for b in result['buttons'] if b))
    result['columns'] = list(dict.fromkeys(c for c in result['columns'] if c))
    # Дедупликация полей по label
    seen_labels = set()
    deduped = []
    for f in result['fields']:
        key = f.get('label', '').lower()
        if key and key not in seen_labels:
            seen_labels.add(key)
            deduped.append(f)
    result['fields'] = deduped

    return result


def _walk(node, src: bytes, result: dict):
    """Рекурсивно обходит AST и собирает UI-элементы."""
    if node.type == 'jsx_element' or node.type == 'jsx_self_closing_element':
        _handle_jsx_element(node, src, result)

    for child in node.children:
        _walk(child, src, result)


_BUTTON_TAGS = {'button', 'cbutton', 'iconbutton', 'fab', 'loadingbutton',
                'submitbutton', 'muibutton'}
_LABEL_TAGS = {'label', 'cformlabel', 'inputlabel', 'formlabel'}
_COLUMN_TAGS = {'ctableheadercell', 'th', 'tablecell', 'tableheadercell',
                'headercell', 'column', 'datagridcolumn'}
_INPUT_SUFFIXES = ('control', 'input', 'field', 'select', 'picker',
                   'autocomplete', 'textarea', 'combobox', 'datepicker',
                   'timepicker', 'checkbox', 'switch', 'radio')
_INPUT_TAGS = {'input', 'textarea', 'textfield', 'inputbase', 'cforminput',
               'select', 'cformselect', 'autocomplete', 'forminput'}


def _handle_jsx_element(node, src: bytes, result: dict):
    """Обрабатывает один JSX элемент."""
    tag = _get_tag_name(node, src)
    if not tag:
        return

    tag_lower = tag.lower()
    props = _get_props(node, src)

    # Кнопки
    if tag_lower in _BUTTON_TAGS:
        text = _get_text_content(node, src)
        if text and 3 <= len(text) <= 50:
            result['buttons'].append(text)
        return

    # Лейблы
    if tag_lower in _LABEL_TAGS:
        text = _get_text_content(node, src)
        if text and len(text) < 80:
            result['fields'].append({'label': text, 'placeholder': '', 'type': 'label'})
        return

    # Колонки таблицы
    if tag_lower in _COLUMN_TAGS:
        text = (_get_text_content(node, src) or
                props.get('headerName') or props.get('header') or props.get('label'))
        if text and len(text) < 60:
            result['columns'].append(text)
        return

    # Заголовки страницы
    if tag_lower in ('h1', 'h2', 'h3') or (tag_lower == 'typography' and
                                              props.get('variant', '') in ('h1', 'h2', 'h3', 'h4')):
        if not result['title']:
            text = _get_text_content(node, src)
            if text and len(text) < 100:
                result['title'] = text
        return

    # Chip / статусные метки
    if tag_lower in ('chip', 'badge', 'tag'):
        label = props.get('label') or _get_text_content(node, src)
        if label and len(label) < 40 and '{' not in label:
            result['chips'].append(label)
        return

    # Поля ввода — стандартные теги ИЛИ кастомные компоненты с label/placeholder
    is_input_tag = tag_lower in _INPUT_TAGS
    is_input_suffix = any(tag_lower.endswith(s) for s in _INPUT_SUFFIXES)
    has_label_prop = 'label' in props or 'placeholder' in props

    if is_input_tag or (is_input_suffix and has_label_prop):
        field = _extract_field(props, tag_lower)
        if field:
            result['fields'].append(field)
        return

    # Любой компонент с label пропом (общий случай для кастомных UI-библиотек)
    if has_label_prop and tag[0].isupper():
        label = props.get('label', '')
        placeholder = props.get('placeholder', '')
        if label and '{' not in label and len(label) < 80:
            result['fields'].append({'label': label, 'placeholder': placeholder, 'type': 'custom'})
        elif placeholder and '{' not in placeholder and len(placeholder) < 80:
            result['fields'].append({'label': placeholder, 'placeholder': placeholder, 'type': 'custom'})


def _extract_field(props: dict, tag_type: str) -> dict | None:
    import re as _re
    label = (props.get('label') or props.get('placeholder') or
             props.get('name') or props.get('id') or '')
    placeholder = props.get('placeholder', '')
    input_type = props.get('type', 'text')

    # Пропускаем скрытые и технические поля
    if input_type in ('hidden', 'submit', 'reset'):
        return None
    if not label and not placeholder:
        return None

    # Чистим JSX-выражения и HTML-теги из значения label
    label = _re.sub(r'<[^>]+>', '', str(label)).strip()
    label = label.replace('{', '').replace('}', '').strip()
    placeholder = _re.sub(r'<[^>]+>', '', str(placeholder)).strip()
    placeholder = placeholder.replace('{', '').replace('}', '').strip()

    display = label or placeholder
    if not display or len(display) < 2:
        return None

    return {'label': display, 'placeholder': placeholder, 'type': input_type}


def _extract_select(props: dict, node, src: bytes, tag: str) -> dict | None:
    label = props.get('label') or props.get('placeholder') or props.get('name', '')
    if not label or '{' in label:
        return None
    return {'label': label, 'options': []}


def _get_tag_name(node, src: bytes) -> str:
    """Возвращает имя тега JSX элемента."""
    try:
        if node.type == 'jsx_self_closing_element':
            name_node = node.child_by_field_name('name')
        else:
            open_tag = node.child_by_field_name('open_tag')
            name_node = open_tag.child_by_field_name('name') if open_tag else None

        if name_node:
            return src[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ''


def _get_props(node, src: bytes) -> dict:
    """Извлекает props JSX элемента."""
    props = {}
    try:
        open_tag = (node if node.type == 'jsx_self_closing_element'
                    else node.child_by_field_name('open_tag'))
        if not open_tag:
            return props

        for attr in open_tag.children:
            if attr.type != 'jsx_attribute':
                continue
            named = attr.named_children
            if not named:
                continue
            name_node = named[0]
            name = src[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore')
            if len(named) > 1:
                val_node = named[1]
                val = src[val_node.start_byte:val_node.end_byte].decode('utf-8', errors='ignore')
                # Для строк берём содержимое без кавычек
                if val_node.type == 'string' and val_node.named_children:
                    frag = val_node.named_children[0]
                    val = src[frag.start_byte:frag.end_byte].decode('utf-8', errors='ignore')
                else:
                    val = val.strip('"\'`')
                props[name] = val
            else:
                # boolean prop без значения: <Component disabled />
                props[name] = True
    except Exception:
        pass
    return props


def _get_text_content(node, src: bytes) -> str:
    """Собирает текстовое содержимое JSX элемента (без дочерних компонентов)."""
    texts = []
    try:
        for child in node.children:
            if child.type == 'jsx_text':
                t = src[child.start_byte:child.end_byte].decode('utf-8', errors='ignore').strip()
                if t:
                    texts.append(t)
            # Строковые литералы в {}
            elif child.type == 'jsx_expression':
                for subchild in child.children:
                    if subchild.type == 'string':
                        t = src[subchild.start_byte:subchild.end_byte].decode(
                            'utf-8', errors='ignore').strip('"\'`')
                        if t:
                            texts.append(t)
    except Exception:
        pass
    text = ' '.join(texts).strip()
    # Убираем JSX-мусор
    if '{' in text or '=>' in text:
        return ''
    return text


def _empty() -> dict:
    return {
        'fields': [],
        'buttons': [],
        'columns': [],
        'selects': [],
        'chips': [],
        'title': '',
    }
