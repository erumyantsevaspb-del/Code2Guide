from types import SimpleNamespace

from core.services.document_builder import build_document_pages


project = SimpleNamespace(
    name="CRM-система для малого бизнеса"
)

instructions = [
    {
        "title": "Проверка корректности заполнения формы",
        "url": "/forms/validation",
        "steps": [
            "Заполните обязательные поля формы.",
            "Выберите необходимые значения.",
            "Нажмите кнопку «Отправить форму».",
        ],
        "tip": "Проверьте правильность введённых данных перед отправкой."
    }
]

pages = build_document_pages(
    project,
    instructions,
)

print("\n=== DOCUMENT PAGES ===")

for page in pages:
    print(page)

print("======================")