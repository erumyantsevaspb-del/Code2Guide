from core.services.react_parser import parse_routes

routes = parse_routes(
    r"C:\Users\Lena\coreui-free-react-admin-template\src\routes.js"
)

print("=== ИНСТРУКЦИЯ CODE2GUIDE ===\n")

for route in routes:
    print(f"Раздел: {route['name']}")
    print(f"URL: {route['path']}")
    print(f"Компонент: {route['component']}")
    print("-" * 40)