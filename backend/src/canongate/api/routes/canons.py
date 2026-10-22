"""Canon management routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from canongate.api.deps import get_canon, list_canon_ids

router = APIRouter(prefix="/canons", tags=["canons"])


class CanonSummary(BaseModel):
    id: str
    version: str
    hash: str
    term_count: int
    color_count: int
    fact_count: int


@router.get("", response_model=list[CanonSummary])
async def list_canons() -> list[CanonSummary]:
    summaries = []
    for cid in list_canon_ids():
        canon = get_canon(cid)
        summaries.append(
            CanonSummary(
                id=canon.id,
                version=canon.version,
                hash=canon.hash,
                term_count=len(canon.terminology),
                color_count=len(canon.palette),
                fact_count=len(canon.facts),
            )
        )
    return summaries


@router.get("/{canon_id}", response_model=CanonSummary)
async def get_canon_detail(canon_id: str) -> CanonSummary:
    canon = get_canon(canon_id)
    return CanonSummary(
        id=canon.id,
        version=canon.version,
        hash=canon.hash,
        term_count=len(canon.terminology),
        color_count=len(canon.palette),
        fact_count=len(canon.facts),
    )
