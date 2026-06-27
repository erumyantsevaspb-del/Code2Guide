def build_document_pages(project, instructions):
    """
    Формирует страницы документа.
    """

    pages = []

    # Титульный лист
    pages.append({
        "page_type": "cover",
        "title": project.name,
        "subtitle": "Руководство пользователя",
        "version": "1.0",
        "generated_date": "14 июня 2026",
        "generated_by": "Code2Guide",
    })

    # Содержание
    contents = []

    page_number = 3

    for instruction in instructions:
        contents.append({
            "title": instruction["name"],
            "page": page_number,
        })
        page_number += 1

    pages.append({
        "page_type": "contents",
        "title": "Содержание",
        "items": contents,
    })

    # Инструкции
    for instruction in instructions:
        pages.append({
            "page_type": "instruction",
            "title": instruction["name"],
            "url": instruction.get("path", ""),
            "steps": instruction["instructions"],
            "screenshot": instruction.get("screenshot"),
            "tip": "",
        })

    return pages