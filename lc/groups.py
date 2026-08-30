"""User-defined problem groups (~/.algocoach/groups.json).

A group is an ordered, nestable "practice plan": it records slugs (the
project's canonical problem key - frontend ids may be non-numeric, see
PITFALLS) plus a parent pointer, so a plan like 2026/0830 is a tree. Groups
never copy problem data; a shared plan travels as slug references only.

Why a dedicated index file (same reasoning as lc/favorites.py): the tree is
tiny, mutated rarely, and must render without touching the problem cache.
Storage contract mirrors favorites:
- whole-file read/write under one lock; plain reads stay lock-free on
  purpose - the atomic replace keeps readers from torn content and
  lc.atomicio's rename retry absorbs the Windows sharing-violation window
- corrupt payloads degrade to an empty tree instead of crashing rendering
- unknown slugs are tolerated (rendered as "unresolved" until a sync
  resolves them); unsafe ones are dropped at the door (lc.validate)

Storage shape is FLAT with parent pointers, not nested children: moving a
whole subtree, cycle checks and depth checks are all one pointer walk, and
sibling order is simply the list order.

Nesting is bounded at MAX_DEPTH - a defensive cap for hand-edited files and
hostile share codes; normal use never approaches it. Moves are cycle-checked
along the parent chain. Share codes carry a versioned prefix and compress
with the stdlib only (zlib + urlsafe base64), keeping the zero-dependency
policy intact.
"""

from __future__ import annotations

import base64
import json
import threading
import uuid
import zlib

from lc.atomicio import atomic_write_text
from lc.config import groups_path
from lc.exceptions import (
    GroupCycleError,
    GroupDepthError,
    GroupNotFoundError,
    GroupShareCodeError,
)
from lc.validate import is_safe_slug

_LOCK = threading.Lock()

SCHEMA = 1
SHARE_PREFIX = "algocoach-groups:v1:"

# defensive caps only - a real plan never approaches them; they exist so a
# hand-edited file or a hostile share code cannot blow up the tree render,
# the lock window or the import parser
MAX_DEPTH = 10
MAX_NAME_LEN = 64
MAX_IMPORT_GROUPS = 500
MAX_IMPORT_SLUGS = 5000


def _resolve(path):
    return path if path is not None else groups_path()


def _clean_name(raw) -> str:
    name = str(raw or "").strip()
    if not name:
        name = "group"
    return name[:MAX_NAME_LEN]


def _clean_slugs(raw) -> list:
    """Safe, deduplicated, order-preserving slug list from arbitrary input."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for slug in raw:
        slug = str(slug or "")
        if slug and is_safe_slug(slug) and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def _depth_map(groups) -> dict:
    """group id -> depth (roots = 1). Pre-seeding the memo terminates even if
    a hand-edited file still contains a parent cycle."""
    depths = {}
    by_id = {g["id"]: g for g in groups}

    def walk(group):
        if group["id"] in depths:
            return depths[group["id"]]
        depths[group["id"]] = 1
        parent = by_id.get(group["parent"]) if group["parent"] else None
        depths[group["id"]] = 1 if parent is None else walk(parent) + 1
        return depths[group["id"]]

    for group in groups:
        walk(group)
    return depths


def _sanitize(payload) -> dict:
    """Normalize a stored document; tolerate corruption like favorites does."""
    raw_groups = payload.get("groups") if isinstance(payload, dict) else None
    if not isinstance(raw_groups, list):
        return {"schema": SCHEMA, "groups": []}

    groups = []
    seen_ids = set()
    for raw in raw_groups:
        if not isinstance(raw, dict):
            continue
        gid = str(raw.get("id") or "")
        if not gid or gid in seen_ids:
            gid = uuid.uuid4().hex[:12]
        seen_ids.add(gid)
        parent = raw.get("parent")
        entry = {
            "id": gid,
            "name": _clean_name(raw.get("name")),
            "parent": parent if isinstance(parent, str) and parent else None,
            "slugs": _clean_slugs(raw.get("slugs")),
        }
        marked = _clean_slugs(raw.get("marked"))
        if marked:
            entry["marked"] = marked
        groups.append(entry)

    # dangling / self parents fall back to root; parent cycles (only possible
    # in a hand-edited file) are cut by re-rooting the node that closes the loop
    ids = {g["id"] for g in groups}
    by_id = {g["id"]: g for g in groups}
    for group in groups:
        walked = set()
        cursor = group
        while cursor["parent"] is not None:
            parent_id = cursor["parent"]
            if parent_id not in ids or parent_id == cursor["id"] or parent_id in walked:
                cursor["parent"] = None
                break
            walked.add(cursor["id"])
            cursor = by_id[parent_id]

    # depth clamp: recompute and re-root until nothing exceeds the cap
    while True:
        depths = _depth_map(groups)
        deep = [g for g in groups if depths[g["id"]] > MAX_DEPTH]
        if not deep:
            break
        for group in deep:
            group["parent"] = None

    return {"schema": SCHEMA, "groups": groups}


def load_groups(path=None) -> list:
    source = _resolve(path)
    if not source.exists():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return _sanitize(payload)["groups"]


def _save_locked(groups, target) -> None:
    """Write the index atomically; caller must hold _LOCK."""
    atomic_write_text(
        target,
        json.dumps({"schema": SCHEMA, "groups": groups}, ensure_ascii=False, indent=2)
        + "\n",
    )


def _find(groups, group_id):
    for group in groups:
        if group["id"] == group_id:
            return group
    return None


def _require_found(groups, group_id) -> dict:
    group = _find(groups, group_id)
    if group is None:
        raise GroupNotFoundError(f"group not found: {group_id!r}")
    return group


def _children_map(groups) -> dict:
    children = {}
    for group in groups:
        children.setdefault(group["parent"], []).append(group["id"])
    return children


def _subtree_ids(groups, root_id) -> set:
    children = _children_map(groups)
    out = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(children.get(current, []))
    return out


def _subtree_height(groups, root_id) -> int:
    """Levels in the subtree, counting itself (a leaf = 1)."""
    children = _children_map(groups)
    height = 0
    stack = [(root_id, 0)]
    while stack:
        current, level = stack.pop()
        level += 1
        height = max(height, level)
        stack.extend((cid, level) for cid in children.get(current, []))
    return height


def _new_id(groups) -> str:
    taken = {g["id"] for g in groups}
    while True:
        candidate = uuid.uuid4().hex[:12]
        if candidate not in taken:
            return candidate


# ---------------------------------------------------------------------------
# tree operations (read-modify-write under one lock, like favorites)


def create_group(name, parent=None, path=None) -> dict:
    with _LOCK:
        all_groups = load_groups(path)
        if parent is not None:
            parent_group = _require_found(all_groups, str(parent))
            depths = _depth_map(all_groups)
            if depths[parent_group["id"]] + 1 > MAX_DEPTH:
                raise GroupDepthError(
                    f"child of {parent_group['id']!r} would exceed {MAX_DEPTH} levels"
                )
        group = {
            "id": _new_id(all_groups),
            "name": _clean_name(name),
            "parent": str(parent) if parent is not None else None,
            "slugs": [],
        }
        all_groups.append(group)
        _save_locked(all_groups, _resolve(path))
    return group


def rename_group(group_id, name, path=None) -> dict:
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        group["name"] = _clean_name(name)
        _save_locked(all_groups, _resolve(path))
    return group


def delete_group(group_id, path=None) -> dict:
    """Cascade delete: the subtree goes with the group."""
    with _LOCK:
        all_groups = load_groups(path)
        _require_found(all_groups, group_id)
        doomed = _subtree_ids(all_groups, group_id)
        removed_slugs = sum(len(g["slugs"]) for g in all_groups if g["id"] in doomed)
        all_groups = [g for g in all_groups if g["id"] not in doomed]
        _save_locked(all_groups, _resolve(path))
    return {"removed_groups": len(doomed), "removed_slugs": removed_slugs}


def move_group(group_id, new_parent, index=None, path=None) -> dict:
    """Re-parent and/or reorder among siblings.

    `index` positions the group among its new siblings (after self-removal,
    clamped); None appends at the end, so both "change parent" and "move
    up/down" are the same operation.
    """
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        if new_parent is not None:
            new_parent = str(new_parent)
            parent_group = _require_found(all_groups, new_parent)
            if new_parent in _subtree_ids(all_groups, group_id):
                raise GroupCycleError(
                    f"{group_id!r} cannot become a descendant of itself"
                )
            depths = _depth_map(all_groups)
            height = _subtree_height(all_groups, group_id)
            # the subtree would occupy depths[parent]+1 .. depths[parent]+height
            if depths[parent_group["id"]] + height > MAX_DEPTH:
                raise GroupDepthError(
                    f"moving under {new_parent!r} would exceed {MAX_DEPTH} levels"
                )
        all_groups.remove(group)
        group["parent"] = new_parent
        siblings = [g for g in all_groups if g["parent"] == new_parent]
        if index is None or not siblings:
            position = len(all_groups)
        else:
            index = max(0, min(int(index), len(siblings)))
            if index == len(siblings):
                # past the last sibling = append after it (the "move down"
                # at the bottom edge must still land last)
                position = all_groups.index(siblings[-1]) + 1
            else:
                position = all_groups.index(siblings[index])
        all_groups.insert(position, group)
        _save_locked(all_groups, _resolve(path))
    return group


def add_slugs(group_id, slugs, path=None) -> dict:
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        cleaned = []
        for slug in slugs or []:
            slug = str(slug or "")
            if not slug:
                continue
            if not is_safe_slug(slug):
                raise ValueError(f"invalid problem slug: {slug!r}")
            if slug not in cleaned:
                cleaned.append(slug)
        existing = set(group["slugs"])
        added = [slug for slug in cleaned if slug not in existing]
        group["slugs"] = group["slugs"] + added
        _save_locked(all_groups, _resolve(path))
    return {"added": len(added), "slugs": list(group["slugs"])}


def remove_slug(group_id, slug, path=None) -> dict:
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        slug = str(slug or "")
        group["slugs"] = [s for s in group["slugs"] if s != slug]
        # a removed problem cannot stay marked
        if group.get("marked"):
            group["marked"] = [s for s in group["marked"] if s != slug]
            if not group["marked"]:
                del group["marked"]
        _save_locked(all_groups, _resolve(path))
    return {"slugs": list(group["slugs"])}


def set_marked(group_id, slugs, path=None) -> dict:
    """Replace the group's key-problem marks ("重点" emphasis in the UI).

    Marks outside the group's slugs are dropped so the stored document never
    references items the group does not contain; an empty result removes the
    key entirely to keep groups.json lean.
    """
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        members = set(group["slugs"])
        marked = [s for s in _clean_slugs(slugs) if s in members]
        if marked:
            group["marked"] = marked
        else:
            group.pop("marked", None)
        _save_locked(all_groups, _resolve(path))
    return {"marked": list(group.get("marked", []))}


def set_order(group_id, slugs, path=None) -> dict:
    """Replace the item order; the payload must be a permutation."""
    with _LOCK:
        all_groups = load_groups(path)
        group = _require_found(all_groups, group_id)
        wanted = [str(s or "") for s in slugs or []]
        if sorted(wanted) != sorted(group["slugs"]):
            raise ValueError("order payload must be a permutation of the group's slugs")
        group["slugs"] = wanted
        _save_locked(all_groups, _resolve(path))
    return {"slugs": list(group["slugs"])}


# ---------------------------------------------------------------------------
# share codes: export (nested) -> zlib -> urlsafe base64, versioned prefix


def export_groups(group_ids=None, path=None) -> dict:
    """Nested snapshot of the selected subtrees (None = the whole forest)."""
    all_groups = load_groups(path)
    if group_ids:
        wanted = set()
        for group_id in group_ids:
            _require_found(all_groups, group_id)
            wanted |= _subtree_ids(all_groups, group_id)
        all_groups = [g for g in all_groups if g["id"] in wanted]
    children = _children_map(all_groups)
    by_id = {g["id"]: g for g in all_groups}

    def node(group):
        entry = {
            "name": group["name"],
            "slugs": list(group["slugs"]),
            "children": [
                node(by_id[cid])
                for cid in children.get(group["id"], [])
                if cid in by_id
            ],
        }
        # marks travel with the code so a shared plan keeps its emphasis
        if group.get("marked"):
            entry["marked"] = list(group["marked"])
        return entry

    roots = [g for g in all_groups if g["parent"] not in by_id]
    return {"schema": SCHEMA, "groups": [node(g) for g in roots]}


def encode_share(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return SHARE_PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")


def decode_share(code: str) -> dict:
    text = str(code or "").strip()
    if not text.startswith(SHARE_PREFIX):
        raise GroupShareCodeError("missing algocoach share-code prefix")
    try:
        raw = zlib.decompress(
            base64.urlsafe_b64decode(text[len(SHARE_PREFIX):].encode("ascii"))
        )
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, zlib.error) as exc:
        # binascii/json errors all subclass ValueError; zlib.error does not
        raise GroupShareCodeError(f"corrupted share code: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != SCHEMA
        or not isinstance(payload.get("groups"), list)
    ):
        raise GroupShareCodeError("unrecognized share-code payload")
    return payload


def _flatten_import(node, depth, out, counters) -> None:
    """Validate one nested node into a cleaned entry (children attached)."""
    if not isinstance(node, dict):
        raise GroupShareCodeError("malformed group node")
    if depth > MAX_DEPTH:
        raise GroupDepthError(f"share code nests deeper than {MAX_DEPTH} levels")
    counters["groups"] += 1
    if counters["groups"] > MAX_IMPORT_GROUPS:
        raise GroupShareCodeError("share code exceeds the group limit")
    slugs = _clean_slugs(node.get("slugs"))
    counters["slugs"] += len(slugs)
    if counters["slugs"] > MAX_IMPORT_SLUGS:
        raise GroupShareCodeError("share code exceeds the problem limit")
    # marks referencing slugs the group does not carry are dropped
    marked = [s for s in _clean_slugs(node.get("marked")) if s in set(slugs)]
    entry = {
        "name": _clean_name(node.get("name")),
        "slugs": slugs,
        "marked": marked,
        "children": [],
    }
    out.append(entry)
    children = node.get("children")
    for child in children if isinstance(children, list) else []:
        _flatten_import(child, depth + 1, entry["children"], counters)


def import_groups(code, path=None) -> dict:
    """Import a share code as NEW top-level groups; unknown slugs are kept
    (they render as unresolved until a sync resolves them), unsafe ones are
    dropped. A root name colliding with an existing root gets a numeric
    suffix so the import stays visible instead of merging silently."""
    payload = decode_share(code)
    cleaned = []
    counters = {"groups": 0, "slugs": 0}
    for root_node in payload["groups"]:
        _flatten_import(root_node, 1, cleaned, counters)

    with _LOCK:
        all_groups = load_groups(path)
        taken_root_names = {g["name"] for g in all_groups if g["parent"] is None}
        created = 0

        def materialize(entry, parent_id) -> dict:
            nonlocal created
            group = {
                "id": _new_id(all_groups),
                "name": entry["name"],
                "parent": parent_id,
                "slugs": list(entry["slugs"]),
            }
            if entry["marked"]:
                group["marked"] = list(entry["marked"])
            all_groups.append(group)
            created += 1
            for child in entry["children"]:
                materialize(child, group["id"])
            return group

        root_ids = []
        for entry in cleaned:
            if entry["name"] in taken_root_names:
                suffix = 2
                while f"{entry['name']} ({suffix})" in taken_root_names:
                    suffix += 1
                entry["name"] = f"{entry['name']} ({suffix})"
            taken_root_names.add(entry["name"])
            root_ids.append(materialize(entry, None)["id"])
        _save_locked(all_groups, _resolve(path))
    return {"created": created, "slugs": counters["slugs"], "root_ids": root_ids}
