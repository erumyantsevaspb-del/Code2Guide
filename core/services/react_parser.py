import re
from pathlib import Path


def parse_component_imports(routes_path):
    """
    Извлекает соответствие:
    компонент -> путь к файлу
    """

    with open(routes_path, encoding="utf-8") as f:
        content = f.read()

    imports = {}

    pattern = (
        r'const\s+(\w+)\s*='
        r'\s*React\.lazy\(\(\)\s*=>\s*import\('
        r"['\"](.+?)['\"]"
    )

    matches = re.findall(
        pattern,
        content
    )

    for component, path in matches:
        imports[component] = path

    return imports

def parse_routes(file_path):
    """
    Извлекает маршруты из routes.js
    """

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    routes = []

    pattern = (
        r"\{\s*path:\s*'([^']+)'.*?"
        r"name:\s*'([^']+)'.*?"
        r"element:\s*(\w+)"
    )

    matches = re.findall(
        pattern,
        content,
        re.DOTALL
    )

    for path, name, component in matches:
        routes.append({
            "path": path,
            "name": name,
            "component": component,
        })

    return routes