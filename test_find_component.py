from core.services.jsx_parser import find_component_file


file = find_component_file(
    repo_path="tests",
    relative_path="./views/forms/validation/Validation"
)

print(file)