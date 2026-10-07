"""
Хранение результатов экспериментов.
Каждый запуск сохраняется в отдельный файл — результаты не перезаписываются.
Формат: experiment_results/<project_id>_<algorithm_version>_<generation_id>.json
"""
import json
from pathlib import Path
from django.conf import settings


def save_experiment_result(generation) -> str:
    """
    Сохраняет результат генерации в отдельный JSON-файл.
    Возвращает путь к файлу.
    Вызывается после завершения генерации (status=completed).
    """
    results_dir = Path(settings.BASE_DIR) / 'experiment_results'
    results_dir.mkdir(exist_ok=True)

    project_id = generation.project_id or 'unknown'
    filename = f"p{project_id}_{generation.algorithm_version}_g{generation.id}.json"
    filepath = results_dir / filename

    data = {
        'experiment': {
            'algorithm_version': generation.algorithm_version,
            'code_version': generation.code_version,
            'generation_id': generation.id,
            'project_id': project_id,
            'project_name': generation.project.name if generation.project else '',
            'created_at': generation.created_at.isoformat() if generation.created_at else None,
            'completed_at': generation.completed_at.isoformat() if generation.completed_at else None,
            'duration_seconds': generation.duration_seconds,
            'status': generation.status,
            'routes_count': generation.components_count,
        },
        'documentation': generation.instruction_data,
    }

    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(filepath)
