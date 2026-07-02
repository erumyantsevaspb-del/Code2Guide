"""
Парсит Django бэкенд из ZIP-архива.
Извлекает verbose_name полей моделей и enum-значения.
Возвращает контекст для генератора инструкций.
"""
import re
import zipfile
from pathlib import Path


def parse_backend_zip(zip_path) -> dict:
    """
    Читает ZIP бэкенда, парсит models.py и enums.py по всем apps/.
    Возвращает словарь:
    {
      'app_name': {
        'fields': {'field_name': 'Человекочитаемое название'},
        'enums': {'ClassName': {'VALUE': 'Перевод'}},
        'docstring': 'Описание модели',
      }
    }
    """
    result = {}

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            names = z.namelist()
            for name in names:
                if 'node_modules' in name or '.git/' in name:
                    continue
                if not name.endswith('.py'):
                    continue

                try:
                    raw = z.read(name)
                    content = _decode(raw)
                except Exception:
                    continue

                # Определяем имя приложения из пути
                app_name = _extract_app_name(name)
                if not app_name:
                    continue

                if app_name not in result:
                    result[app_name] = {'fields': {}, 'enums': {}, 'docstring': ''}

                if name.endswith('models.py'):
                    _parse_models(content, result[app_name])
                elif 'enum' in name.lower() or 'const' in name.lower() or 'choice' in name.lower():
                    _parse_enums(content, result[app_name])

    except Exception as e:
        print(f"Ошибка парсинга бэкенда: {e}")

    return result


# Ручные синонимы: слова в маршруте → имя приложения в бэкенде
_ROUTE_APP_SYNONYMS = {
    'claims': 'tickets',
    'tickets': 'tickets',
    'заявки': 'tickets',
    'заявка': 'tickets',
    'appoints': 'appointments',
    'appointment': 'appointments',
    'приём': 'appointments',
    'приемы': 'appointments',
    'consumables': 'materials',
    'materials': 'materials',
    'расходники': 'materials',
    'extra': 'dop_uslugi',
    'dop': 'dop_uslugi',
    'услуги': 'dop_uslugi',
    'statements': 'reports',
    'reports': 'reports',
    'отчеты': 'reports',
    'patients': 'appointments',
    'deals': 'appointments',
    'salary': 'wagework',
    'wagework': 'wagework',
}


def get_route_context(backend_context: dict, route_path: str, route_name: str) -> dict:
    """
    Находит наиболее подходящий app для маршрута.
    Сначала проверяет синонимы, потом совпадение слов.
    """
    if not backend_context:
        return {}

    route_key = route_path.strip('/').split('/')[0].lower().replace('-', '_')
    route_words = re.split(r'[_\-/\s]', route_key + ' ' + route_name.lower())

    # 1. Проверяем синонимы
    for word in route_words:
        mapped = _ROUTE_APP_SYNONYMS.get(word.lower())
        if mapped and mapped in backend_context:
            return backend_context[mapped]

    # 2. Прямое совпадение слов с именем приложения
    route_word_set = set(w for w in route_words if len(w) > 2)
    best_app = None
    best_score = 0

    for app_name, data in backend_context.items():
        if not data['fields']:
            continue
        app_words = set(re.split(r'[_\-]', app_name.lower()))
        score = len(route_word_set & app_words)
        if score > best_score:
            best_score = score
            best_app = app_name

    if best_app and best_score > 0:
        return backend_context[best_app]
    return {}


def _decode(raw: bytes) -> str:
    for enc in ('utf-8', 'cp1251', 'latin-1'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', errors='ignore')


def _extract_app_name(filepath: str) -> str:
    """Извлекает имя приложения из пути вида .../apps/tickets/models.py"""
    parts = filepath.replace('\\', '/').split('/')
    for i, part in enumerate(parts):
        if part == 'apps' and i + 1 < len(parts):
            app = parts[i + 1]
            # пропускаем служебные имена
            if app and not app.endswith('.py') and app not in ('__pycache__', 'migrations'):
                return app
    return ''


def _parse_models(content: str, app_data: dict):
    """Извлекает verbose_name из полей Django моделей."""
    # Docstring модели
    doc_match = re.search(r'class \w+\(models\.Model\):\s+"""(.*?)"""', content, re.DOTALL)
    if doc_match and not app_data['docstring']:
        app_data['docstring'] = doc_match.group(1).strip()

    # verbose_name полей: verbose_name=_('Название') или verbose_name='Название'
    field_pattern = re.compile(
        r'(\w+)\s*=\s*models\.\w+\([^)]*verbose_name\s*=\s*(?:_\()?["\']([^"\']+)["\']',
        re.DOTALL
    )
    for match in field_pattern.finditer(content):
        field_name, verbose = match.group(1), match.group(2).strip()
        if field_name not in ('id', 'Meta') and verbose:
            app_data['fields'][field_name] = verbose


def _parse_enums(content: str, app_data: dict):
    """Извлекает enum-значения из классов с константами."""
    # Ищем классы с переводами: VALUE_TRANSLATED: str = _('Перевод')
    class_pattern = re.compile(r'class (\w+)[^:]*:\s*((?:(?!^class )[\s\S])*)', re.MULTILINE)
    translated_pattern = re.compile(
        r'(\w+?)(?:_TRANSLATED)?\s*:\s*str\s*=\s*(?:_\()?["\']([^"\']+)["\']'
    )

    for cls_match in class_pattern.finditer(content):
        cls_name = cls_match.group(1)
        cls_body = cls_match.group(2)

        translations = {}
        for m in translated_pattern.finditer(cls_body):
            key = m.group(1).rstrip('_TRANSLATED')
            val = m.group(2).strip()
            if val and not val.startswith('{') and len(val) < 80:
                translations[key] = val

        if translations:
            app_data['enums'][cls_name] = translations
