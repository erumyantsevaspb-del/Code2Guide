import re


def generate_instructions_with_yandex(route_name, path, jsx_content):
    """
    Генерирует пошаговую инструкцию на основе JSX-кода без внешнего API.
    """
    fields = _extract_fields(jsx_content)
    selects = _extract_selects(jsx_content)
    checkboxes = _extract_checkboxes(jsx_content)
    buttons = _extract_buttons(jsx_content)

    steps = []

    # Шаг 1: открыть раздел
    steps.append(
        f'Откройте раздел «{route_name}». '
        f'В меню навигации найдите и перейдите в этот раздел.'
    )

    # Шаг 2: заполнить поля (если есть)
    if fields:
        if len(fields) == 1:
            steps.append(
                f'Заполните поле «{fields[0]}». '
                f'Введите необходимое значение в поле ввода.'
            )
        else:
            fields_list = '», «'.join(fields)
            steps.append(
                f'Заполните поля формы: «{fields_list}». '
                f'Введите соответствующие данные в каждое поле.'
            )

    # Шаг 3: выпадающие списки (если есть)
    if selects:
        steps.append(
            'Выберите необходимые значения из выпадающих списков. '
            'Нажмите на список и выберите подходящий вариант.'
        )

    # Шаг 4: чекбоксы (если есть)
    if checkboxes:
        if len(checkboxes) == 1:
            steps.append(
                f'Установите флажок «{checkboxes[0]}» если необходимо.'
            )
        else:
            checks_list = '», «'.join(checkboxes)
            steps.append(
                f'Отметьте нужные параметры: «{checks_list}».'
            )

    # Шаг 5: кнопка действия
    if buttons:
        main_button = _pick_main_button(buttons)
        steps.append(
            f'Нажмите кнопку «{main_button}» для подтверждения. '
            f'После этого данные будут сохранены.'
        )
    elif fields or selects:
        steps.append(
            'Нажмите кнопку подтверждения для сохранения данных.'
        )

    # Если ничего не нашли — базовые шаги
    if len(steps) == 1:
        steps.append('Ознакомьтесь с содержимым раздела.')
        steps.append('Используйте доступные функции для работы с данными.')

    return steps


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
    return list(dict.fromkeys(result))  # убираем дубли


def _extract_selects(jsx_content):
    return re.findall(r'<(?:CFormSelect|select)', jsx_content)


def _extract_checkboxes(jsx_content):
    checks = re.findall(
        r'<(?:CFormCheck|input[^>]*type=["\']checkbox["\'])[^>]*label=["\']([^"\']+)["\']',
        jsx_content
    )
    return checks


def _extract_buttons(jsx_content):
    buttons = re.findall(
        r'<(?:CButton|button)[^>]*>(.*?)</(?:CButton|button)>',
        jsx_content, re.DOTALL
    )
    result = []
    for btn in buttons:
        btn = re.sub(r'<[^>]+>', '', btn).strip()
        btn = re.sub(r'\s+', ' ', btn)
        if btn and len(btn) < 40:
            result.append(btn)
    return list(dict.fromkeys(result))


def _pick_main_button(buttons):
    priority = ['submit', 'сохранить', 'save', 'отправить', 'send',
                'создать', 'create', 'добавить', 'add', 'войти', 'login']
    for keyword in priority:
        for btn in buttons:
            if keyword in btn.lower():
                return btn
    return buttons[0]
