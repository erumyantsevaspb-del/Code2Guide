import re
from pathlib import Path


def parse_routes(routes_file_path):
    """
    Извлекает маршруты из routes.js
    """

    with open(routes_file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    routes = []

    route_pattern = re.compile(r"\{([^{}]+)\}")

    for route_match in route_pattern.finditer(content):
        route_text = route_match.group(1)

        path_match = re.search(r"path:\s*'([^']+)'", route_text)
        name_match = re.search(r"name:\s*'([^']+)'", route_text)
        element_match = re.search(r"element:\s*([A-Za-z0-9_]+)", route_text)

        if path_match and name_match:
            routes.append({
                'path': path_match.group(1),
                'name': name_match.group(1),
                'component': element_match.group(1) if element_match else None,
            })

    return routes