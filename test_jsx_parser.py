from core.services.jsx_parser import parse_jsx_instructions


instructions = parse_jsx_instructions(
    "tests/Validation.jsx"
)

print("\nНайденные действия:\n")

for i, instruction in enumerate(instructions, start=1):
    print(f"{i}. {instruction}")