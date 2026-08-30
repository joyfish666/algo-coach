"""Group store (lc.groups) + /api/groups endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from server import app as app_module

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def client():
    return TestClient(app_module.app, base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# unit level: lc.groups store


def test_group_crud_cascade_and_order(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    root = groups.create_group("2026", path=store)
    child = groups.create_group("0830", parent=root["id"], path=store)
    sibling = groups.create_group("0831", parent=root["id"], path=store)

    result = groups.add_slugs(child["id"], ["two-sum", "two-sum", "add-two-numbers"], path=store)
    assert result["added"] == 2
    assert result["slugs"] == ["two-sum", "add-two-numbers"]

    # sibling order follows list order; move up/down repositions the group
    moved = groups.move_group(child["id"], root["id"], index=1, path=store)
    assert moved["id"] == child["id"]
    order = [g["id"] for g in groups.load_groups(store) if g["parent"] == root["id"]]
    assert order == [sibling["id"], child["id"]]
    groups.move_group(child["id"], root["id"], index=0, path=store)
    order = [g["id"] for g in groups.load_groups(store) if g["parent"] == root["id"]]
    assert order == [child["id"], sibling["id"]]

    # reorder must be a permutation of the stored slugs
    groups.set_order(child["id"], ["add-two-numbers", "two-sum"], path=store)
    with pytest.raises(ValueError):
        groups.set_order(child["id"], ["two-sum"], path=store)

    # cascade: deleting the parent removes the whole subtree
    groups.add_slugs(sibling["id"], ["longest-substring"], path=store)
    result = groups.delete_group(root["id"], path=store)
    assert result == {"removed_groups": 3, "removed_slugs": 3}
    assert groups.load_groups(store) == []


def test_move_rejects_cycles(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    root = groups.create_group("A", path=store)
    child = groups.create_group("B", parent=root["id"], path=store)
    grandchild = groups.create_group("C", parent=child["id"], path=store)

    with pytest.raises(groups.GroupCycleError):
        groups.move_group(root["id"], root["id"], path=store)
    with pytest.raises(groups.GroupCycleError):
        groups.move_group(root["id"], grandchild["id"], path=store)
    # moving into a sibling subtree is fine
    groups.move_group(grandchild["id"], child["id"], path=store)


def test_depth_cap(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    current = groups.create_group("level-1", path=store)
    for level in range(2, groups.MAX_DEPTH + 1):
        current = groups.create_group(f"level-{level}", parent=current["id"], path=store)
    assert len(groups.load_groups(store)) == groups.MAX_DEPTH
    with pytest.raises(groups.GroupDepthError):
        groups.create_group("too-deep", parent=current["id"], path=store)

    # moving a tall subtree under a deep parent must respect the same cap
    other_root = groups.create_group("R", path=store)
    other_child = groups.create_group("S", parent=other_root["id"], path=store)
    chain_root = next(g for g in groups.load_groups(store) if g["name"] == "level-1")
    # the chain has height 10: under R (depth 1) it would reach 11
    with pytest.raises(groups.GroupDepthError):
        groups.move_group(chain_root["id"], other_child["id"], path=store)
    with pytest.raises(groups.GroupDepthError):
        groups.move_group(chain_root["id"], other_root["id"], path=store)
    # only the root level can hold it
    moved = groups.move_group(chain_root["id"], None, path=store)
    assert moved["parent"] is None

    # a height-9 chain under a depth-1 root lands exactly at the cap
    chain9 = groups.create_group("h1", path=store)
    for level in range(2, 10):
        chain9 = groups.create_group(f"h{level}", parent=chain9["id"], path=store)
    moved = groups.move_group(
        next(g for g in groups.load_groups(store) if g["name"] == "h1")["id"],
        other_root["id"],
        path=store,
    )
    assert moved["parent"] == other_root["id"]


def test_corrupt_file_degrades_to_empty(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    store.write_text("{not json", encoding="utf-8")
    assert groups.load_groups(store) == []
    assert not store.exists() or store.read_text(encoding="utf-8")


def test_sanitize_repairs_hand_edited_files(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    chain = []
    for level in range(12):
        chain.append({"id": f"g{level}", "name": f"level-{level}", "parent": f"g{level - 1}" if level else None, "slugs": []})
    payload = {
        "schema": 1,
        "groups": [
            *chain,
            {"id": "a", "name": "A", "parent": "b", "slugs": ["two-sum", "bad slug!", "", "two-sum"]},
            {"id": "b", "name": "B", "parent": "a", "slugs": []},
            {"id": "c", "name": "C", "parent": "ghost", "slugs": []},
        ],
    }
    store.write_text(json.dumps(payload), encoding="utf-8")
    repaired = {g["id"]: g for g in groups.load_groups(store)}

    # cycle a<->b is cut, dangling parent falls back to root
    assert repaired["b"]["parent"] is None
    assert repaired["c"]["parent"] is None
    # unsafe and duplicate slugs are dropped
    assert repaired["a"]["slugs"] == ["two-sum"]
    # the 12-deep chain is clamped: nothing nests beyond MAX_DEPTH
    depths = {}
    for group in repaired.values():
        depth, cursor = 1, group
        while cursor["parent"] is not None:
            depth += 1
            cursor = repaired[cursor["parent"]]
        depths[group["id"]] = depth
    assert max(depths.values()) <= groups.MAX_DEPTH


def test_share_code_roundtrip_and_root_collision(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    root = groups.create_group("2026", path=store)
    child = groups.create_group("0830", parent=root["id"], path=store)
    groups.add_slugs(child["id"], ["two-sum"], path=store)

    code = groups.encode_share(groups.export_groups([root["id"]], path=store))
    assert code.startswith(groups.SHARE_PREFIX)

    # importing into a fresh store reproduces the same tree
    fresh = tmp_path / "fresh.json"
    result = groups.import_groups(code, path=fresh)
    assert result["created"] == 2 and result["slugs"] == 1
    imported = groups.load_groups(fresh)
    assert [g["name"] for g in imported] == ["2026", "0830"]
    assert imported[1]["slugs"] == ["two-sum"]

    # importing into a store that already has a same-named root suffixes it
    result = groups.import_groups(code, path=store)
    assert result["created"] == 2
    root_names = sorted(g["name"] for g in groups.load_groups(store) if g["parent"] is None)
    assert root_names == ["2026", "2026 (2)"]


def test_share_code_rejects_garbage_and_overdeep_nesting(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    with pytest.raises(groups.GroupShareCodeError):
        groups.decode_share("not-a-share-code")
    with pytest.raises(groups.GroupShareCodeError):
        groups.decode_share(groups.SHARE_PREFIX + "!!!")
    with pytest.raises(groups.GroupShareCodeError):
        groups.import_groups(groups.SHARE_PREFIX + "!!!", path=store)

    deep = {"name": "0", "slugs": [], "children": []}
    cursor = deep
    for level in range(1, groups.MAX_DEPTH + 2):
        cursor["children"] = [{"name": str(level), "slugs": [], "children": []}]
        cursor = cursor["children"][0]
    code = groups.encode_share({"schema": 1, "groups": [deep]})
    with pytest.raises(groups.GroupDepthError):
        groups.import_groups(code, path=store)

    # unknown (not-yet-synced) slugs survive the import on purpose
    payload = {"schema": 1, "groups": [{"name": "plan", "slugs": ["not-in-cache"], "children": []}]}
    groups.import_groups(groups.encode_share(payload), path=store)
    assert groups.load_groups(store)[0]["slugs"] == ["not-in-cache"]


def test_marked_key_problems_roundtrip(tmp_path):
    from lc import groups

    store = tmp_path / "groups.json"
    root = groups.create_group("数组", path=store)
    groups.add_slugs(root["id"], ["two-sum", "add-two-numbers", "three-sum"], path=store)

    result = groups.set_marked(root["id"], ["two-sum", "three-sum"], path=store)
    assert result["marked"] == ["two-sum", "three-sum"]
    stored = groups.load_groups(store)[0]
    assert stored["marked"] == ["two-sum", "three-sum"]

    # marks outside the group's slugs are dropped, not stored
    result = groups.set_marked(root["id"], ["two-sum", "not-a-member"], path=store)
    assert result["marked"] == ["two-sum"]

    # removing a problem removes its mark; clearing all marks drops the key
    groups.remove_slug(root["id"], "two-sum", path=store)
    stored = groups.load_groups(store)[0]
    assert "marked" not in stored

    # share codes carry the marks both ways
    groups.set_marked(root["id"], ["add-two-numbers"], path=store)
    code = groups.encode_share(groups.export_groups([root["id"]], path=store))
    fresh = tmp_path / "fresh.json"
    groups.import_groups(code, path=fresh)
    imported = groups.load_groups(fresh)[0]
    assert imported["marked"] == ["add-two-numbers"]


# ---------------------------------------------------------------------------
# API level


def test_groups_api_flow(client):
    root = client.post("/api/groups", json={"name": "2026"}, headers=ORIGIN).json()
    child = client.post(
        "/api/groups", json={"name": "0830", "parent": root["id"]}, headers=ORIGIN
    ).json()

    added = client.post(
        f"/api/groups/{child['id']}/items",
        json={"slugs": ["two-sum", "two-sum", "add-two-numbers"]},
        headers=ORIGIN,
    ).json()
    assert added["added"] == 2

    listing = client.get("/api/groups").json()["groups"]
    assert [(g["name"], g["parent"]) for g in listing] == [
        ("2026", None),
        ("0830", root["id"]),
    ]
    assert listing[1]["slugs"] == ["two-sum", "add-two-numbers"]

    reordered = client.put(
        f"/api/groups/{child['id']}/items",
        json={"slugs": ["add-two-numbers", "two-sum"]},
        headers=ORIGIN,
    ).json()
    assert reordered["slugs"] == ["add-two-numbers", "two-sum"]

    client.put(f"/api/groups/{child['id']}/rename", json={"name": "0831"}, headers=ORIGIN)
    moved = client.put(
        f"/api/groups/{child['id']}/move", json={"parent": None}, headers=ORIGIN
    ).json()
    assert moved["parent"] is None

    client.delete(f"/api/groups/{child['id']}/items/two-sum", headers=ORIGIN)
    result = client.delete(f"/api/groups/{root['id']}", headers=ORIGIN).json()
    assert result["deleted"] is True
    assert result["removed_groups"] == 1

    remaining = client.get("/api/groups").json()["groups"]
    assert [g["name"] for g in remaining] == ["0831"]
    assert remaining[0]["slugs"] == ["add-two-numbers"]


def test_groups_api_error_envelopes(client):
    missing = client.put(
        "/api/groups/missing/rename", json={"name": "x"}, headers=ORIGIN
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["message_key"] == "group_not_found"

    root = client.post("/api/groups", json={"name": "A"}, headers=ORIGIN).json()
    child = client.post(
        "/api/groups", json={"name": "B", "parent": root["id"]}, headers=ORIGIN
    ).json()
    cycle = client.put(
        f"/api/groups/{root['id']}/move", json={"parent": child["id"]}, headers=ORIGIN
    )
    assert cycle.status_code == 400
    assert cycle.json()["error"]["message_key"] == "group_cycle"

    bad_order = client.put(
        f"/api/groups/{child['id']}/items", json={"slugs": ["nope"]}, headers=ORIGIN
    )
    assert bad_order.status_code == 422

    current = root
    for level in range(2, 11):
        current = client.post(
            "/api/groups", json={"name": f"level-{level}", "parent": current["id"]},
            headers=ORIGIN,
        ).json()
    too_deep = client.post(
        "/api/groups", json={"name": "too-deep", "parent": current["id"]}, headers=ORIGIN
    )
    assert too_deep.status_code == 400
    assert too_deep.json()["error"]["message_key"] == "group_depth_limit"


def test_groups_api_marked_endpoint(client):
    root = client.post("/api/groups", json={"name": "2026"}, headers=ORIGIN).json()
    client.post(
        f"/api/groups/{root['id']}/items", json={"slugs": ["two-sum"]}, headers=ORIGIN
    )
    marked = client.put(
        f"/api/groups/{root['id']}/marked",
        json={"slugs": ["two-sum", "ghost"]},
        headers=ORIGIN,
    ).json()
    assert marked["marked"] == ["two-sum"]
    listing = client.get("/api/groups").json()["groups"]
    assert listing[0]["marked"] == ["two-sum"]


def test_groups_api_share_code_roundtrip(client):
    root = client.post("/api/groups", json={"name": "2026"}, headers=ORIGIN).json()
    child = client.post(
        "/api/groups", json={"name": "0830", "parent": root["id"]}, headers=ORIGIN
    ).json()
    client.post(
        f"/api/groups/{child['id']}/items", json={"slugs": ["two-sum"]}, headers=ORIGIN
    )

    code = client.post(
        "/api/groups/export", json={"ids": [root["id"]]}, headers=ORIGIN
    ).json()["code"]
    assert code.startswith("algocoach-groups:v1:")

    result = client.post("/api/groups/import", json={"code": code}, headers=ORIGIN).json()
    assert result["created"] == 2 and result["slugs"] == 1

    listing = client.get("/api/groups").json()["groups"]
    root_names = sorted(g["name"] for g in listing if g["parent"] is None)
    assert root_names == ["2026", "2026 (2)"]

    invalid = client.post("/api/groups/import", json={"code": "garbage"}, headers=ORIGIN)
    assert invalid.status_code == 400
    assert invalid.json()["error"]["message_key"] == "group_invalid_code"
