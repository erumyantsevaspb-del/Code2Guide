def build_document_pages(project, instructions):
    """
    Формирует страницы документа.
    """

    pages = []

    pages.append({
        "page_type": "cover",
        "title": project.name,
        "subtitle": "Руководство пользователя",
        "version": "1.0",
        "generated_date": "14 июня 2026",
        "generated_by": "Code2Guide",
    })

    for instruction in instructions:
        pages.append({
            "page_type": "instruction",
            "title": instruction["name"],
            "url": instruction.get("path", ""),
            "steps": instruction["instructions"],
            "tip": "",
        })

    return pages