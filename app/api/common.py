"""Shared API helpers (pagination)."""
from fastapi import Query

from app.core.config import settings


class PageParams:
    """Dependency providing clamped pagination params."""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        limit: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, description="Items per page"),
    ):
        self.page = page
        self.limit = min(limit, settings.MAX_PAGE_SIZE)
        self.offset = (page - 1) * self.limit
