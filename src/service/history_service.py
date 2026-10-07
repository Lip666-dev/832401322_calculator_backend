"""History service: reading, deleting and favouriting stored calculations."""

from __future__ import annotations

import math

from ..config import Settings
from ..errors import NotFoundError, ValidationError
from ..model.history_repository import HistoryRepository


class HistoryService:
    """Use cases behind ``/api/history``."""

    def __init__(self, repository: HistoryRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def list_history(
        self,
        keyword: str | None = None,
        favorites_only: bool = False,
        page: int = 1,
        page_size: int | None = None,
    ) -> dict:
        """Return one page of history, newest first."""
        size = page_size or self._settings.default_page_size
        size = max(1, min(size, self._settings.max_page_size))
        cleaned_keyword = (keyword or "").strip() or None

        records, total = self._repository.list(
            keyword=cleaned_keyword,
            favorites_only=favorites_only,
            page=page,
            page_size=size,
        )
        pages = max(1, math.ceil(total / size))
        return {
            "items": [record.to_dict() for record in records],
            "total": total,
            "page": page,
            "page_size": size,
            "pages": pages,
            "keyword": cleaned_keyword,
            "favorites_only": favorites_only,
        }

    def get_record(self, record_id: int) -> dict:
        record = self._repository.get(record_id)
        if record is None:
            raise NotFoundError(f"History record {record_id} does not exist", id=record_id)
        return record.to_dict()

    def delete_record(self, record_id: int) -> dict:
        """Delete one record, reporting how many rows were removed."""
        deleted = self._repository.delete(record_id)
        if deleted == 0:
            raise NotFoundError(f"History record {record_id} does not exist", id=record_id)
        return {"id": record_id, "deleted": deleted}

    def clear_history(self) -> dict:
        deleted = self._repository.clear()
        return {"deleted": deleted}

    def set_favorite(self, record_id: int, is_favorite: bool) -> dict:
        updated = self._repository.set_favorite(record_id, is_favorite)
        if updated == 0:
            raise NotFoundError(f"History record {record_id} does not exist", id=record_id)
        return {"id": record_id, "is_favorite": is_favorite, "updated": updated}

    def require_positive_page(self, page: int) -> int:
        if page < 1:
            raise ValidationError("The page number must be >= 1", field="page")
        return page
