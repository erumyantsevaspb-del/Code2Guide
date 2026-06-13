import re


def parse_jsx_instructions(file_path):
    """
    Извлекает пользовательские действия из JSX-файла.
    """

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    instructions = []

    # Поля ввода
    labels = re.findall(
        r'<CFormLabel[^>]*>(.*?)</CFormLabel>',
        content,
        re.DOTALL
    )

    for label in labels:
        label = label.strip()

        if label:
            instructions.append(
                f'Введите значение в поле "{label}".'
            )

    # Выпадающие списки
    selects = re.findall(
        r'<CFormSelect',
        content
    )

    for _ in selects:
        instructions.append(
            'Выберите значение из выпадающего списка.'
        )

    # Чекбоксы
    checkboxes = re.findall(
        r'<CFormCheck[^>]*label="([^"]+)"',
        content
    )

    for checkbox in checkboxes:
        instructions.append(
            f'Установите флажок "{checkbox}".'
        )

    # Кнопки
    buttons = re.findall(
        r'<CButton[^>]*>(.*?)</CButton>',
        content,
        re.DOTALL
    )

    for button in buttons:

        button = re.sub(
            r'\s+',
            ' ',
            button
        ).strip()

        if button:
            instructions.append(
                f'Нажмите кнопку "{button}".'
            )

    unique_instructions = []

    for instruction in instructions:
        if instruction not in unique_instructions:
            unique_instructions.append(instruction)

    return unique_instructions