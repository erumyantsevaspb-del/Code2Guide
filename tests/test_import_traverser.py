"""
Тесты collect_ui_from_component — рекурсивный обход импортов.

Покрывает:
  - страница-обёртка с дочерним компонентом (поля, кнопки)
  - вложенность 2 уровня
  - повторный импорт одного компонента (не дублируется)
  - циклические импорты (не зависает)
  - неразрешённый импорт (пропускается)
  - дочерний без полезных элементов (не влияет)
  - алиасные импорты (directory-alias)
  - barrel-alias (пропускается)
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.services.import_traverser import collect_ui_from_component


def _make_project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel_path, content in files.items():
        full = Path(tmp) / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
    return tmp


# ── базовые кейсы ─────────────────────────────────────────────────────

def test_single_file_with_fields():
    """Файл без импортов: поля из самого файла."""
    src = _make_project({
        'src/pages/Form.tsx': '''
export default function Form() {
  return (
    <form>
      <label>Имя</label>
      <input type="text" placeholder="Введите имя" />
      <button>Сохранить</button>
    </form>
  );
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/pages/Form.tsx'), src, max_depth=0
    )
    assert len(result['fields']) >= 1, f"Ожидались поля, получили: {result['fields']}"
    assert len(result['buttons']) >= 1, f"Ожидались кнопки, получили: {result['buttons']}"
    print(f"  PASS test_single_file_with_fields: fields={[f['label'] for f in result['fields']]}")


def test_wrapper_with_child_fields():
    """Страница-обёртка с дочерним компонентом через relative import."""
    src = _make_project({
        'src/pages/CreatePage.tsx': '''
import { CreateForm } from './CreateForm';
export default function CreatePage() {
  return <CreateForm />;
}
''',
        'src/pages/CreateForm.tsx': '''
export function CreateForm() {
  return (
    <form>
      <label>Фамилия</label>
      <input type="text" placeholder="Введите фамилию" />
      <label>Имя</label>
      <button>Создать</button>
    </form>
  );
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/pages/CreatePage.tsx'), src, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    assert any('Фамилия' in l or 'Имя' in l or 'фамилию' in l for l in labels), \
        f"Должны найти поля из дочернего компонента, получили: {labels}"
    assert 'Создать' in result['buttons'], f"Кнопка из дочернего, buttons={result['buttons']}"
    print(f"  PASS test_wrapper_with_child_fields: fields={labels}, buttons={result['buttons']}")


def test_two_level_nesting():
    """Глубина 2: страница → виджет → форма."""
    src = _make_project({
        'src/Page.tsx': '''
import { Widget } from './Widget';
export default function Page() { return <Widget />; }
''',
        'src/Widget.tsx': '''
import { DeepForm } from './DeepForm';
export function Widget() { return <DeepForm />; }
''',
        'src/DeepForm.tsx': '''
export function DeepForm() {
  return (
    <form>
      <label>Телефон</label>
      <button>Отправить</button>
    </form>
  );
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=3
    )
    labels = [f['label'] for f in result['fields']]
    assert any('Телефон' in l for l in labels), f"Должен найти поле на 2 уровне, fields={labels}"
    assert 'Отправить' in result['buttons']
    print(f"  PASS test_two_level_nesting: fields={labels}")


def test_repeated_import_no_duplicate():
    """Один дочерний компонент импортирован несколько раз — поля не дублируются."""
    src = _make_project({
        'src/Page.tsx': '''
import { Form } from './Form';
import { Form as FormAlias } from './Form';
export default function Page() { return <><Form /><FormAlias /></>; }
''',
        'src/Form.tsx': '''
export function Form() {
  return <form><label>Email</label><button>Ок</button></form>;
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=2
    )
    email_fields = [f for f in result['fields'] if 'email' in f['label'].lower()]
    assert len(email_fields) == 1, f"Поле Email должно быть ровно одним, fields={result['fields']}"
    ok_buttons = [b for b in result['buttons'] if 'Ок' in b or 'email' in b.lower()]
    # Файл посещается только один раз — дублей нет
    assert len(email_fields) <= 1, f"Нет дублей полей: {result['fields']}"
    print(f"  PASS test_repeated_import_no_duplicate: fields={result['fields']}")


def test_circular_import_no_infinite_loop():
    """Циклический импорт A→B→A не вешает traversal."""
    src = _make_project({
        'src/A.tsx': '''
import { B } from './B';
export function A() { return <><B /><label>Поле A</label></>; }
''',
        'src/B.tsx': '''
import { A } from './A';
export function B() { return <><A /><label>Поле B</label></>; }
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/A.tsx'), src, max_depth=5
    )
    labels = [f['label'] for f in result['fields']]
    assert any('Поле' in l for l in labels), f"Должны найти хотя бы одно поле: {labels}"
    print(f"  PASS test_circular_import_no_infinite_loop: fields={labels}")


def test_unresolvable_import_skipped():
    """Неразрешённый импорт не падает, остальные поля находятся."""
    src = _make_project({
        'src/Page.tsx': '''
import { Ghost } from './NonExistentFile';
export default function Page() {
  return <form><label>Настоящее поле</label><button>Готово</button></form>;
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    assert any('Настоящее' in l or 'поле' in l.lower() for l in labels), \
        f"Должен найти поля в текущем файле: {labels}"
    print(f"  PASS test_unresolvable_import_skipped: fields={labels}")


def test_empty_child_no_effect():
    """Дочерний компонент без элементов — не ломает результат."""
    src = _make_project({
        'src/Page.tsx': '''
import { EmptyChild } from './EmptyChild';
export default function Page() {
  return (
    <div>
      <EmptyChild />
      <form><label>Поле страницы</label></form>
    </div>
  );
}
''',
        'src/EmptyChild.tsx': '''
export function EmptyChild() { return <div>no fields here</div>; }
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    assert any('страниц' in l.lower() or 'поле' in l.lower() for l in labels), \
        f"Должен найти поле страницы: {labels}"
    print(f"  PASS test_empty_child_no_effect: fields={labels}")


def test_depth_zero_no_children():
    """max_depth=0: только текущий файл, дочерние не анализируются."""
    src = _make_project({
        'src/Page.tsx': '''
import { Form } from './Form';
export default function Page() { return <Form />; }
''',
        'src/Form.tsx': '''
export function Form() {
  return <form><label>Поле формы</label><button>Сохранить</button></form>;
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=0
    )
    # С depth=0 дочерний файл не анализируется
    assert 'Сохранить' not in result['buttons'], f"depth=0 не должен идти в дочерние: {result}"
    print(f"  PASS test_depth_zero_no_children")


def test_directory_alias_import():
    """Directory-alias: widgets/foo → widgets-dir/foo.tsx."""
    src = _make_project({
        'src/Page.tsx': '''
import { FilterWidget } from 'widgets/filters';
export default function Page() { return <FilterWidget />; }
''',
        'widgets-dir/filters.tsx': '''
export function FilterWidget() {
  return (
    <form>
      <label>Дата начала</label>
      <label>Дата конца</label>
      <button>Найти</button>
    </form>
  );
}
''',
    })
    alias_map = {'widgets': 'widgets-dir'}
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src,
        alias_map=alias_map, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    assert any('Дата' in l for l in labels), f"Directory alias должен разрешиться: {labels}"
    assert 'Найти' in result['buttons']
    print(f"  PASS test_directory_alias_import: fields={labels}")


def test_test_file_not_followed():
    """Импорт, который разрешается в тестовый файл (в /test/ директории), не следуется."""
    src = _make_project({
        'src/Page.tsx': '''
import { utils } from './TestUtils';
export default function Page() {
  return <form><label>Реальное поле</label><button>Сохранить</button></form>;
}
''',
        'src/test/TestUtils.tsx': '''
export const utils = {};
export function TestUtils() {
  return <form><label>Тестовое поле</label></form>;
}
''',
    })
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    # Тестовый файл не должен добавлять свои поля
    assert not any('Тестовое' in l for l in labels), \
        f"Поля из тестового файла не должны попасть: {labels}"
    assert any('Реальное' in l for l in labels), \
        f"Поля из основного файла должны быть: {labels}"
    print(f"  PASS test_test_file_not_followed: fields={labels}")


def test_barrel_alias_skipped():
    """Barrel-alias (точное совпадение) пропускается."""
    src = _make_project({
        'src/Page.tsx': '''
import { Button } from '@shared/ui';
export default function Page() {
  return <form><label>Собственное поле</label><button>Кнопка</button></form>;
}
''',
    })
    alias_map = {'@shared/ui': 'libs/ui/index'}
    result = collect_ui_from_component(
        str(Path(src) / 'src/Page.tsx'), src,
        alias_map=alias_map, max_depth=2
    )
    labels = [f['label'] for f in result['fields']]
    # Barrel не разрешается, поля только из текущего файла
    assert any('Собственное' in l or 'поле' in l.lower() for l in labels), f"{labels}"
    print(f"  PASS test_barrel_alias_skipped: fields={labels}")


# ── runner ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_single_file_with_fields,
        test_wrapper_with_child_fields,
        test_two_level_nesting,
        test_repeated_import_no_duplicate,
        test_circular_import_no_infinite_loop,
        test_unresolvable_import_skipped,
        test_empty_child_no_effect,
        test_depth_zero_no_children,
        test_directory_alias_import,
        test_test_file_not_followed,
        test_barrel_alias_skipped,
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("import_traverser — тесты")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}\n")

    import sys
    sys.exit(0 if failed == 0 else 1)
