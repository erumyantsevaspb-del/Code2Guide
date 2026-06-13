from core.services.react_parser import parse_component_imports


imports = parse_component_imports(
    "tests/routes.js"
)

print("\nНайденные импорты:\n")

for component, path in imports.items():
    print(f"{component} -> {path}")