import re


def beautify_instructions(instructions):
    """
    Делает инструкции более человекочитаемыми.
    """

    result = []

    text_fields = []
    textareas = []
    checkboxes = []
    buttons = []

    has_dropdowns = False

    for instruction in instructions:

        # Поля ввода
        # Поля ввода
        match = re.search(
            r'Введите значение в поле "(.+?)"',
            instruction
        )

        if match:
            field_name = match.group(1)

            if field_name.lower() == "textarea":
                textareas.append(field_name)
            else:
                text_fields.append(field_name)

            continue

        # Чекбоксы
        match = re.search(
            r'Установите флажок "(.+?)"',
            instruction
        )

        if match:
            checkboxes.append(match.group(1))
            continue

        # Кнопки
        match = re.search(
            r'Нажмите кнопку "(.+?)"',
            instruction
        )

        if match:
            buttons.append(match.group(1))
            continue

        # Выпадающие списки
        if "выпадающего списка" in instruction:
            has_dropdowns = True
            continue

        result.append(instruction)

    if text_fields:
        result.append(
            "Заполните обязательные поля формы: "
            + ", ".join(text_fields)
            + "."
        )

    if textareas:
        result.append(
            "При необходимости укажите дополнительную информацию "
            "в текстовом поле."
        )

    if has_dropdowns:
        result.append(
            "Выберите необходимые значения из выпадающих списков."
        )

    if checkboxes:
        result.append(
            "Подтвердите необходимые согласия "
            "и выберите дополнительные параметры формы."
        )

    for button in buttons:
        result.append(
            f'Нажмите кнопку «{button}» для отправки данных.'
        )

    return result