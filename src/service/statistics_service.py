"""Statistics service: an extended feature that summarises stored history."""

from __future__ import annotations

from ..model.history_repository import HistoryRepository


class StatisticsService:
    """Aggregate numbers about the stored calculations."""

    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    def summarize(self) -> dict:
        return self._repository.statistics()
