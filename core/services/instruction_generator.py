import re


def generate_instructions_with_yandex(route_name, path, jsx_content, backend_context=None):
    """
    Генерирует пошаговую инструкцию на основе JSX-кода и контекста бэкенда.
    """
    fields = _extract_fields(jsx_content)
    selects = _extract_selects(jsx_content)
    checkboxes = _extract_checkboxes(jsx_content)
    buttons = _extract_buttons(jsx_content)

    # Обогащаем названия полей из бэкенда
    be_fields = backend_context.get('fields', {}) if backend_context else {}
    be_enums = backend_context.get('enums', {}) if backend_context else {}

    # Человекочитаемые названия фильтров/полей
    resolved_fields = _resolve_fields(fields, be_fields)
    enum_values = _collect_enum_values(be_enums)
    status_values = _find_status_values(be_enums)

    steps = []

    # Шаг 1: открыть раздел
    steps.append(f'Откройте раздел «{route_name}» в меню навигации.')

    # Шаг 2: фильтры/поиск (если есть поля и дропдауны — это список с поиском)
    is_list_page = selects and (fields or selects)
    if is_list_page and resolved_fields:
        filter_list = ', '.join(f'«{f}»' for f in resolved_fields[:6])
        steps.append(
            f'Для поиска нужной записи используйте фильтры: {filter_list}. '
            f'Заполните один или несколько фильтров и нажмите «Поиск».'
        )
    elif resolved_fields and not selects:
        # Форма создания/редактирования
        if len(resolved_fields) == 1:
            steps.append(f'Заполните поле «{resolved_fields[0]}».')
        else:
            fields_list = ', '.join(f'«{f}»' for f in resolved_fields[:8])
            steps.append(f'Заполните поля: {fields_list}.')

    # Шаг 3: статусы (если есть)
    if status_values and is_list_page:
        statuses = ', '.join(f'«{s}»' for s in status_values[:6])
        steps.append(f'Записи можно фильтровать по статусу: {statuses}.')

    # Шаг 4: чекбоксы
    if checkboxes:
        if len(checkboxes) == 1:
            steps.append(f'При необходимости отметьте «{checkboxes[0]}».')
        else:
            checks_list = ', '.join(f'«{c}»' for c in checkboxes[:5])
            steps.append(f'Отметьте нужные параметры: {checks_list}.')

    # Шаг 5: основная кнопка действия
    if buttons:
        main_button = _pick_main_button(buttons)
        if is_list_page and main_button.lower() in ('поиск', 'найти', 'search', 'filter'):
            pass  # уже упомянули в шаге фильтров
        else:
            steps.append(f'Нажмите «{main_button}» для подтверждения действия.')

    # Шаг 6: результат действия (если есть статусы в форме — значит меняется статус)
    if status_values and not is_list_page:
        statuses = ', '.join(f'«{s}»' for s in status_values[:4])
        steps.append(f'После сохранения статус записи изменится. Возможные статусы: {statuses}.')

    # Если ничего не нашли
    if len(steps) == 1:
        steps.append('Ознакомьтесь с содержимым раздела и доступными действиями.')

    return steps


def _resolve_fields(jsx_fields, be_fields):
    """
    Заменяет технические имена полей из JSX на verbose_name из бэкенда.
    Если совпадений нет — оставляет JSX-значения.
    """
    if not be_fields:
        return jsx_fields

    result = list(jsx_fields)  # начинаем с JSX полей

    # Добавляем поля из бэкенда которых нет в JSX (они могут быть важны)
    jsx_lower = {f.lower() for f in jsx_fields}
    for field_name, verbose in be_fields.items():
        if verbose.lower() not in jsx_lower and len(result) < 10:
            # Добавляем только если это похоже на пользовательское поле
            skip = {'id', 'created', 'updated', 'modified', 'datetime', 'has_unread'}
            if not any(s in field_name.lower() for s in skip):
                result.append(verbose)

    return list(dict.fromkeys(result))[:10]


def _collect_enum_values(be_enums):
    """Собирает все enum-значения из бэкенда в один список."""
    values = []
    for cls_vals in be_enums.values():
        values.extend(cls_vals.values())
    return values


def _find_status_values(be_enums):
    """Ищет enum-класс со статусами."""
    for cls_name, vals in be_enums.items():
        if 'status' in cls_name.lower() or 'statuse' in cls_name.lower():
            return list(vals.values())
    return []


def _extract_fields(jsx_content):
    labels = re.findall(
        r'<(?:CFormLabel|label)[^>]*>(.*?)</(?:CFormLabel|label)>',
        jsx_content, re.DOTALL
    )
    result = []
    for label in labels:
        label = re.sub(r'<[^>]+>', '', label).strip()
        label = re.sub(r'\s+', ' ', label)
        if label and len(label) < 60:
            result.append(label)
    return list(dict.fromkeys(result))


def _extract_selects(jsx_content):
    return re.findall(r'<(?:CFormSelect|select|Select|Autocomplete)', jsx_content)


def _extract_checkboxes(jsx_content):
    checks = re.findall(
        r'<(?:CFormCheck|input[^>]*type=["\']checkbox["\'])[^>]*label=["\']([^"\']+)["\']',
        jsx_content
    )
    result = []
    for c in checks:
        c = c.strip()
        if not c or len(c) < 3 or '{' in c or c in ('...', '1', '2', '3'):
            continue
        result.append(c)
    return list(dict.fromkeys(result))[:10]


def _extract_buttons(jsx_content):
    buttons = re.findall(
        r'<(?:CButton|button|Button)[^>]*>(.*?)</(?:CButton|button|Button)>',
        jsx_content, re.DOTALL
    )
    result = []
    for btn in buttons:
        btn = re.sub(r'<[^>]+>', '', btn).strip()
        btn = re.sub(r'\s+', ' ', btn)
        if not btn or len(btn) >= 40:
            continue
        if '{' in btn or '}' in btn or '=>' in btn or btn.startswith('('):
            continue
        result.append(btn)
    return list(dict.fromkeys(result))


def _pick_main_button(buttons):
    priority = ['сохранить', 'save', 'отправить', 'send', 'создать', 'create',
                'добавить', 'add', 'войти', 'login', 'submit', 'подтвердить']
    for keyword in priority:
        for btn in buttons:
            if keyword in btn.lower():
                return btn
    return buttons[0]
