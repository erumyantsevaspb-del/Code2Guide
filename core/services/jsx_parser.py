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

from pathlib import Path

# Суффиксы, которые не являются частью имени компонента:
# appoints.page.tsx → appoints, home.screen.tsx → home
_PAGE_SUFFIXES = ('.page', '.screen', '.view', '.container', '.layout')


def _strip_page_suffix(stem: str) -> str:
    lower = stem.lower()
    for suf in _PAGE_SUFFIXES:
        if lower.endswith(suf):
            return stem[: len(stem) - len(suf)]
    return stem


def _norm(name: str) -> str:
    """Нормализует имя: salary.history → salary_history, aligner-form → aligner_form."""
    return name.replace('.', '_').replace('-', '_').lower()


def _plural_variants(norm_name: str) -> set:
    """
    Возвращает set нормализованных имён с вариантом ±s на последнем сегменте.
    statements_revenues_months → {statements_revenues_months, statements_revenues_month}
    manage_center             → {manage_center, manage_centers}
    """
    variants = {norm_name}
    parts = norm_name.rsplit('_', 1)
    if len(parts) == 2:
        last = parts[1]
        if last.endswith('s') and len(last) > 1:
            variants.add(parts[0] + '_' + last[:-1])   # months → month
        else:
            variants.add(parts[0] + '_' + last + 's')  # center → centers
    return variants


def find_component_file(repo_path, relative_path):
    """
    Ищет js/jsx/tsx файл компонента по явному относительному пути (из imports).
    """

    extensions = [
        ".js",
        ".jsx",
        ".tsx",
    ]

    for ext in extensions:

        candidate = (
            Path(repo_path)
            / "src"
            / relative_path.replace(
                "./",
                ""
            )
        )

        candidate = Path(
            str(candidate) + ext
        )

        if candidate.exists():
            return candidate

    return None


def find_component_by_name(repo_path, component_name):
    """
    Ищет файл компонента по имени класса/функции когда явного пути нет.

    Стратегия: ищем {Name}.tsx / {Name}.jsx / {Name}.js рекурсивно в src/,
    затем {Name}/index.tsx|jsx|js, затем те же паттерны в корне проекта.
    Пропускаем node_modules. Возвращает первое совпадение или None.
    """
    if not component_name:
        return None

    repo = Path(repo_path)
    extensions = ('.tsx', '.jsx', '.js')

    search_roots = []
    src = repo / 'src'
    if src.is_dir():
        search_roots.append(src)
    search_roots.append(repo)

    norm_component = _norm(component_name)

    for root in search_roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob('*'):
            if 'node_modules' in candidate.parts:
                continue
            if not candidate.is_file():
                continue
            if candidate.suffix not in extensions:
                continue
            stem = candidate.stem

            # 1. Точное совпадение: Dashboard.tsx → Dashboard
            if stem.lower() == component_name.lower():
                return candidate

            # 2. Суффикс .page/.screen/.view: appoints.page.tsx → appoints
            base = _strip_page_suffix(stem)
            if base.lower() == component_name.lower():
                return candidate

            # 3. Нормализация точек/дефисов: duty.schedule → duty_schedule
            if _norm(base) == norm_component:
                return candidate

            # 4. Вариант ±s на последнем сегменте: month↔months, center↔centers
            if _norm(base) in _plural_variants(norm_component):
                return candidate

            # 4. index.tsx в директории: Settings/index.tsx → Settings
            if stem.lower() == 'index':
                dir_base = _strip_page_suffix(candidate.parent.name)
                if (candidate.parent.name.lower() == component_name.lower() or
                        _norm(dir_base) == norm_component):
                    return candidate

    return None