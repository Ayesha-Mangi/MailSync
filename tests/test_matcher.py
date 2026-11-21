import pytest

from backend import matcher
from tests.fakes import FakeDB

VECS = {"laptop-lost": [1, 0, 0], "laptop-found": [0.95, 0.1, 0], "keys-found": [1, 0, 0], "far": [0, 1, 0]}


@pytest.fixture
def env(monkeypatch):
    db, sent = FakeDB(), []
    monkeypatch.setattr(matcher, "get_supabase", lambda: db)
    monkeypatch.setattr(matcher, "generate_embedding", lambda text: VECS[text.split("|")[1].strip()])
    monkeypatch.setattr(matcher, "send_match_notification", lambda *a, **k: sent.append(a) or True)
    return db, sent


def item(intent, key, category="Electronics"):
    return {"intent": intent, "item_name": key, "category": category, "color": "Unknown",
            "brand": "Unknown", "location": "Library", "event_date_time": "Unknown", "summary": key}


def test_lost_then_found_matches_and_emails_both(env):
    db, sent = env
    assert matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")["status"] == "stored"
    res = matcher.process_and_match_item(item("found", "laptop-found"), "b@u.edu", "m2")
    assert res["status"] == "matched" and res["match"]["similarity"] > 0.78
    assert {r["status"] for r in db.tables["items"]} == {"matched"}
    assert len(db.tables["matches"]) == 1 and db.tables["matches"][0]["notified"] is True
    assert {s[0] for s in sent} == {"a@u.edu", "b@u.edu"}


def test_duplicate_message_id_ignored(env):
    db, _ = env
    matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")
    assert matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")["status"] == "duplicate"
    assert len(db.tables["items"]) == 1


def test_category_mismatch_does_not_match(env):
    matcher.process_and_match_item(item("lost", "laptop-lost", "Electronics"), "a@u.edu", "m1")
    assert matcher.process_and_match_item(item("found", "keys-found", "Keys"), "b@u.edu", "m2")["status"] == "stored"


def test_below_threshold_does_not_match(env):
    matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")
    assert matcher.process_and_match_item(item("found", "far"), "b@u.edu", "m2")["status"] == "stored"


def test_same_sender_never_matches_self(env):
    matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")
    assert matcher.process_and_match_item(item("found", "laptop-found"), "a@u.edu", "m2")["status"] == "stored"


def test_same_intent_never_matches(env):
    matcher.process_and_match_item(item("lost", "laptop-lost"), "a@u.edu", "m1")
    assert matcher.process_and_match_item(item("lost", "laptop-found"), "b@u.edu", "m2")["status"] == "stored"
