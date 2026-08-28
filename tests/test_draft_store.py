import json

from game.draft_store import DRAFTS_DIR, DraftStore


def test_draft_store_save_load_delete(tmp_path, monkeypatch):
    monkeypatch.setattr("game.draft_store.DRAFTS_DIR", tmp_path)

    store = DraftStore("profile-1")
    store.save(
        "character_test",
        {
            "kind": "character_create",
            "fields": {"name": "艾拉", "background": "斥候", "world_id": "fantasy"},
        },
    )

    loaded = store.load("character_test")
    assert loaded is not None
    assert loaded["fields"]["name"] == "艾拉"
    assert "updated_at" in loaded

    path = tmp_path / "profile-1" / "character_test.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["fields"]["background"] == "斥候"

    store.delete("character_test")
    assert not path.exists()
    assert store.load("character_test") is None


def test_draft_store_scopes_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("game.draft_store.DRAFTS_DIR", tmp_path)

    guest = DraftStore("_guest")
    guest.save("new_profile", {"fields": {"name": "小明"}})

    profile = DraftStore("profile-a")
    profile.save("new_profile", {"fields": {"name": "朋友 A"}})

    assert guest.load("new_profile")["fields"]["name"] == "小明"
    assert profile.load("new_profile")["fields"]["name"] == "朋友 A"
