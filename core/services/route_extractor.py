"""
Интерфейс экстракторов маршрутов.

RouteCandidate — стандартный формат маршрута. Поля path/name/component/approximate
совместимы с форматом, который уже потребляют views.py и screenshot_service.py.
Новые поля source_file и warnings имеют значения по умолчанию, поэтому
существующие потребители, не ожидающие этих полей, не сломаются.

ExtractResult — обёртка результата с метаданными экстрактора.

Классы-обёртки делегируют работу существующим функциям из react_parser.py —
их внутренняя логика не изменена.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from typing_extensions import TypedDict, NotRequired


class RouteCandidate(TypedDict):
    path: str
    name: str
    component: str
    approximate: bool
    source_file: NotRequired[str]
    warnings: NotRequired[list[str]]


class ExtractResult(TypedDict):
    routes: list[RouteCandidate]
    extractor_name: str
    partial: bool
    error: Optional[str]


def _wrap_routes(raw: list[dict], extractor_name: str) -> list[RouteCandidate]:
    """Превращает dict-список из react_parser в список RouteCandidate."""
    result: list[RouteCandidate] = []
    for r in raw:
        candidate: RouteCandidate = {
            'path': r.get('path', '/'),
            'name': r.get('name', ''),
            'component': r.get('component', ''),
            'approximate': r.get('approximate', False),
        }
        if 'source_file' in r:
            candidate['source_file'] = r['source_file']
        if 'warnings' in r:
            candidate['warnings'] = r['warnings']
        result.append(candidate)
    return result


class BaseExtractor(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, app_root: Path) -> ExtractResult:
        ...

    def _make_result(
        self,
        raw: list[dict],
        partial: bool = False,
        error: Optional[str] = None,
    ) -> ExtractResult:
        return ExtractResult(
            routes=_wrap_routes(raw, self.name),
            extractor_name=self.name,
            partial=partial,
            error=error,
        )


class RoutePathExtractor(BaseExtractor):
    """Обёртка для parse_routepath_routes (кастомный TS-роутер)."""
    name = "routepath"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_routepath_routes
        try:
            raw = parse_routepath_routes(str(app_root))
            return self._make_result(raw)
        except Exception as e:
            return self._make_result([], error=str(e))


class NextJSExtractor(BaseExtractor):
    """Обёртка для parse_nextjs_routes (App Router) + parse_nextjs_pages_routes."""
    name = "nextjs"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_nextjs_routes, parse_nextjs_pages_routes
        try:
            raw = parse_nextjs_routes(str(app_root))
            if not raw:
                raw = parse_nextjs_pages_routes(str(app_root))
            return self._make_result(raw)
        except Exception as e:
            return self._make_result([], error=str(e))


class ReactAdminExtractor(BaseExtractor):
    """Обёртка для parse_react_admin_routes."""
    name = "react_admin"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_react_admin_routes
        try:
            raw = parse_react_admin_routes(str(app_root))
            return self._make_result(raw)
        except Exception as e:
            return self._make_result([], error=str(e))


class JSXExtractor(BaseExtractor):
    """Обёртка для parse_jsx_routes (React Router v4-v7 JSX)."""
    name = "jsx"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_jsx_routes
        try:
            raw = parse_jsx_routes(str(app_root))
            return self._make_result(raw)
        except Exception as e:
            return self._make_result([], error=str(e))


class BrowserRouterExtractor(BaseExtractor):
    """Обёртка для parse_browser_router_routes (createBrowserRouter)."""
    name = "browser_router"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_browser_router_routes
        try:
            raw = parse_browser_router_routes(str(app_root))
            return self._make_result(raw)
        except Exception as e:
            return self._make_result([], error=str(e))


class FallbackExtractor(BaseExtractor):
    """Обёртка для parse_component_pages_fallback (эвристика по директориям).

    Всегда устанавливает partial=True: результаты приблизительные.
    """
    name = "fallback"

    def extract(self, app_root: Path) -> ExtractResult:
        from core.services.react_parser import parse_component_pages_fallback
        try:
            raw = parse_component_pages_fallback(str(app_root))
            return self._make_result(raw, partial=bool(raw))
        except Exception as e:
            return self._make_result([], error=str(e))
