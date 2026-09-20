# mvp/engine/ocr/course_cache.py
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CourseMetadataCache:
    """
    Caches scorecard metadata so we only OCR the scorecard once per course.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = str(Path(__file__).resolve().parent / "cache")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.current_course: Optional[str] = None
        self.metadata: Optional[Dict[str, Any]] = None

    def _cache_path(self, course_name: str) -> Path:
        safe_name = course_name.replace(" ", "_").lower()
        return self.cache_dir / f"{safe_name}.json"

    def _load_from_disk(self, course_name: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(course_name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load course metadata from disk")
            return None

    def _save_to_disk(self, course_name: str, data: Dict[str, Any]):
        try:
            path = self._cache_path(course_name)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to save course metadata")

    def get_metadata(self, course_name: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.metadata is not None and self.current_course == course_name:
            return self.metadata

        cached = self._load_from_disk(course_name)
        if cached:
            self.metadata = cached
            self.current_course = course_name
            return cached

        self.metadata = raw_data
        self.current_course = course_name
        self._save_to_disk(course_name, raw_data)
        return raw_data

    def clear_cache(self):
        self.metadata = None
        self.current_course = None
