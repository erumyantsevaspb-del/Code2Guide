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

from core.services.react_parser import parse_routes

routes = parse_routes(routes_path)

print("\nКоличество найденных маршрутов:")
print(len(routes))

print("\nПервые 5 маршрутов:")

for route in routes[:5]:
    print(route)