from django.utils.timezone import now


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
        "generated_date": now().strftime("%-d %B %Y") if hasattr(now(), 'strftime') else "",
        "generated_by": "Code2Guide",
    })

    # Страница "О системе" если есть бизнес-контекст
    business_context = getattr(project, 'business_context', '') or ''
    if business_context.strip():
        pages.append({
            "page_type": "about",
            "title": "О системе",
            "content": business_context.strip(),
        })

    # Содержание
    contents = []
    page_number = len(pages) + 2  # +1 содержание, +1 первая инструкция

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