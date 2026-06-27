import shutil
import tempfile
import zipfile
from pathlib import Path

from .github_service import clone_repository


def prepare_project_source(project):
    """
    Returns (source_path, cleanup_path).

    source_path is the folder that contains the React project.
    cleanup_path is the temporary folder that should be removed after parsing.
    """
    if project.react_archive:
        return extract_react_archive(project.react_archive.path)

    if project.repo_url:
        repo_path = clone_repository(
            project.repo_url,
            project.branch or "main",
        )
        return repo_path, repo_path

    raise ValueError("Upload a ZIP archive or specify a repository URL.")


def extract_react_archive(archive_path):
    if not zipfile.is_zipfile(archive_path):
        raise ValueError("Uploaded file must be a ZIP archive.")

    temp_dir = Path(tempfile.mkdtemp(prefix="code2guide_"))

    try:
        with zipfile.ZipFile(archive_path) as archive:
            safe_extract(archive, temp_dir)

        project_root = find_react_project_root(temp_dir)
        return str(project_root), str(temp_dir)

    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def safe_extract(archive, target_dir):
    target_dir = target_dir.resolve()

    for member in archive.infolist():
        destination = (target_dir / member.filename).resolve()

        if not str(destination).startswith(str(target_dir)):
            raise ValueError("ZIP archive contains unsafe paths.")

    archive.extractall(target_dir)


def find_react_project_root(extracted_dir):
    # Сначала ищем CoreUI-style routes.js
    route_files = sorted(
        extracted_dir.rglob("src/routes.js"),
        key=lambda path: len(path.parts),
    )
    if route_files:
        return route_files[0].parent.parent

    # Потом ищем ближайший package.json (любой React-проект)
    package_files = sorted(
        extracted_dir.rglob("package.json"),
        key=lambda path: len(path.parts),
    )
    # Фильтруем node_modules
    package_files = [p for p in package_files if 'node_modules' not in p.parts]
    if package_files:
        return package_files[0].parent

    return extracted_dir
