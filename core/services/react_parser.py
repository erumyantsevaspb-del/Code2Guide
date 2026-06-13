import re
from pathlib import Path


def parse_routes(routes_file_path):
    """
    Извлекает маршруты из routes.js
    """

    with open(routes_file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    pattern = re.compile(
        r"\{\s*path:\s*'([^']+)'.*?name:\s*'([^']+)'.*?(?:element:\s*([A-Za-z0-9_]+))?",
        re.DOTALL
    )

    routes = []

    for match in pattern.finditer(content):
        path = match.group(1)
        name = match.group(2)
        component = match.group(3)

        routes.append({
            'path': path,
            'name': name,
            'component': component,
        })

    return routes