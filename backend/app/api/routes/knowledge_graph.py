from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.graph.public_store import (
    PublicGraphAmbiguous,
    PublicGraphNotFound,
    PublicGraphStore,
    PublicGraphUnavailable,
)
from app.schemas.knowledge_graph import (
    KnowledgeGraphMetaResponse,
    KnowledgeGraphNodeDetailResponse,
    KnowledgeGraphResponse,
    KnowledgeGraphSearchResponse,
)

router = APIRouter(prefix="/knowledge-graph", tags=["知识图谱"])


def _store(request: Request) -> PublicGraphStore:
    return request.app.state.public_graph_store


def _headers(response: Response, version: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = f'"{version}"'


@router.get("/meta", response_model=KnowledgeGraphMetaResponse)
def meta(request: Request, response: Response) -> KnowledgeGraphMetaResponse:
    try:
        result = _store(request).meta()
        _headers(response, result.version)
        return result
    except PublicGraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "知识图谱暂不可用。") from exc


@router.get("/search", response_model=KnowledgeGraphSearchResponse)
def search(
    request: Request,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=160)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> KnowledgeGraphSearchResponse:
    try:
        result = _store(request).search(q, limit)
        _headers(response, result.version)
        return result
    except PublicGraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "知识图谱暂不可用。") from exc


@router.get("/nodes/{node_id}", response_model=KnowledgeGraphNodeDetailResponse)
def node_detail(
    node_id: str, request: Request, response: Response
) -> KnowledgeGraphNodeDetailResponse:
    try:
        result = _store(request).detail(node_id)
        _headers(response, result.version)
        return result
    except PublicGraphNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图谱实体不存在。") from exc
    except PublicGraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "知识图谱暂不可用。") from exc


@router.get("", response_model=KnowledgeGraphResponse)
def graph(
    request: Request,
    response: Response,
    center: Annotated[str | None, Query(max_length=160)] = None,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    limit: Annotated[int, Query(ge=25, le=500)] = 250,
    types: Annotated[list[str] | None, Query()] = None,
    relations: Annotated[list[str] | None, Query()] = None,
    include_sources: bool = False,
) -> KnowledgeGraphResponse:
    try:
        result = _store(request).graph(
            center=center,
            depth=depth,
            limit=limit,
            types=set(types or ()),
            relations=set(relations or ()),
            include_sources=include_sources,
        )
        _headers(response, result.version)
        return result
    except PublicGraphAmbiguous as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "实体别名存在歧义。",
                "candidates": [item.model_dump() for item in exc.candidates],
            },
        ) from exc
    except PublicGraphNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图谱实体不存在。") from exc
    except PublicGraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "知识图谱暂不可用。") from exc
