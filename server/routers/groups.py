"""User-defined problem groups: tree CRUD, item ordering, share codes.

Thin transport over lc.groups; every mutating op is a whole-file
read-modify-write under the module lock there, so no extra locking here.
ValueErrors raised by the core (unsafe slugs, non-permutation reorders)
answer 422; domain exceptions (unknown group, cycle, depth, corrupt share
code) flow through the unified envelope with message_keys.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lc import groups
from lc.logutil import logger

router = APIRouter()


@router.get("/api/groups")
def get_groups():
    return {"groups": groups.load_groups()}


class GroupCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=groups.MAX_NAME_LEN)
    parent: str | None = None


@router.post("/api/groups")
def create_group(payload: GroupCreatePayload):
    group = groups.create_group(payload.name, payload.parent)
    logger.info("group created: %s %r", group["id"], group["name"])
    return group


class GroupRenamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=groups.MAX_NAME_LEN)


@router.put("/api/groups/{group_id}/rename")
def rename_group(group_id: str, payload: GroupRenamePayload):
    return groups.rename_group(group_id, payload.name)


class GroupMovePayload(BaseModel):
    parent: str | None = None
    index: int | None = None


@router.put("/api/groups/{group_id}/move")
def move_group(group_id: str, payload: GroupMovePayload):
    return groups.move_group(group_id, payload.parent, payload.index)


@router.delete("/api/groups/{group_id}")
def delete_group(group_id: str):
    result = groups.delete_group(group_id)
    logger.info("group deleted: %s %s", group_id, result)
    return {"deleted": True, **result}


class SlugsPayload(BaseModel):
    slugs: list[str]


@router.post("/api/groups/{group_id}/items")
def add_items(group_id: str, payload: SlugsPayload):
    try:
        return groups.add_slugs(group_id, payload.slugs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/api/groups/{group_id}/items")
def set_order(group_id: str, payload: SlugsPayload):
    try:
        return groups.set_order(group_id, payload.slugs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/groups/{group_id}/items/{qid}")
def remove_item(group_id: str, qid: str):
    return groups.remove_slug(group_id, qid)


class MarkedPayload(BaseModel):
    slugs: list[str]


@router.put("/api/groups/{group_id}/marked")
def set_marked(group_id: str, payload: MarkedPayload):
    """Replace the group's key-problem marks (UI "重点" emphasis)."""
    result = groups.set_marked(group_id, payload.slugs)
    logger.info("group marks updated: %s (%d)", group_id, len(result["marked"]))
    return result


class ImportPayload(BaseModel):
    code: str = Field(min_length=1)


@router.post("/api/groups/import")
def import_share(payload: ImportPayload):
    result = groups.import_groups(payload.code)
    logger.info("groups imported: %s", result)
    return result


class ExportPayload(BaseModel):
    ids: list[str] | None = None


@router.post("/api/groups/export")
def export_share(payload: ExportPayload):
    return {"code": groups.encode_share(groups.export_groups(payload.ids))}
