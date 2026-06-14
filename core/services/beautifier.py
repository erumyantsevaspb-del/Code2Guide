import re


def beautify_instructions(instructions):
    """
    Делает инструкции более человекочитаемыми.
    """

    result = []

    text_fields = []
    checkboxes = []
    buttons = []

    for instruction in instructions:

        # Поля ввода
        match = re.search(
            r'Введите значение в поле "(.+?)"',
            instruction
        )

        if match:
            text_fields.append(match.group(1))
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
            result.append(
                "Выберите необходимые значения из выпадающих списков."
            )
            continue

        result.append(instruction)

    if text_fields:
        result.append(
            "Заполните обязательные поля формы: "
            + ", ".join(text_fields)
            + "."
        )

    if checkboxes:
        result.append(
            "Подтвердите необходимые согласия: "
            + ", ".join(checkboxes)
            + "."
        )

    for button in buttons:
        result.append(
            f'Нажмите кнопку "{button}" для завершения действия.'
        )

    return result