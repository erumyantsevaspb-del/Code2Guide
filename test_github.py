from core.services.github_service import clone_repository

repo_path = clone_repository(
    "https://github.com/coreui/coreui-free-react-admin-template.git"
)

print("Репозиторий успешно скачан:")
print(repo_path)

from pathlib import Path

routes_path = Path(repo_path) / "src" / "routes.js"

print("\nНайден routes.js:")
print(routes_path)
print(routes_path.exists())

from core.services.react_parser import parse_component_imports

imports = parse_component_imports(routes_path)

print("\nValidation:")
print(imports.get("Validation"))

validation_path = (
    Path(repo_path)
    / "src"
    / imports.get("Validation").replace("./", "")
)

print("\nПуть без расширения:")
print(validation_path)

for ext in [".js", ".jsx", ".tsx"]:
    candidate = Path(str(validation_path) + ext)

    print()
    print(candidate)
    print(candidate.exists())

validation_file = None

for ext in [".js", ".jsx", ".tsx"]:
    candidate = Path(str(validation_path) + ext)

    if candidate.exists():
        validation_file = candidate
        break

print("\nНайденный JSX-файл:")
print(validation_file)

from core.services.jsx_parser import parse_jsx_instructions

instructions = parse_jsx_instructions(validation_file)

print("\nНайденные действия:")

for i, instruction in enumerate(instructions, start=1):
    print(f"{i}. {instruction}")


from core.services.react_parser import parse_routes

routes = parse_routes(routes_path)

print("\nКоличество найденных маршрутов:")
print(len(routes))

print("\nПервые 5 маршрутов:")

for route in routes[:5]:
    print(route)