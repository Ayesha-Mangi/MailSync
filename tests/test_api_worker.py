from fastapi.testclient import TestClient

from backend import api, worker
from tests.fakes import FakeDB


def test_api_webhook_and_items(monkeypatch):
    db, queued = FakeDB(), []
    monkeypatch.setattr(api, "get_supabase", lambda: db)
    monkeypatch.setattr("backend.matcher.get_supabase", lambda: db)
    monkeypatch.setattr(api, "parse_email_content", lambda s, b: {
        "is_lost_or_found": "lost" in s.lower(), "intent": "lost", "item_name": "Keys"})
    monkeypatch.setattr(api, "process_and_match_item", lambda *a, **k: queued.append(a))
    c = TestClient(api.app)

    assert c.get("/health").json() == {"status": "ok"}
    ok = c.post("/webhook/email", json={"subject": "Lost keys", "body": "x", "sender": "Ali <ali@u.edu>", "message_id": "1"})
    assert ok.json()["status"] == "queued" and queued[0][1] == "ali@u.edu"
    noise = c.post("/webhook/email", json={"subject": "Newsletter", "body": "x", "sender": "a@u.edu", "message_id": "2"})
    assert noise.json()["status"] == "ignored"
    bad = c.post("/webhook/email", json={"subject": "Lost", "body": "x", "sender": "nobody", "message_id": "3"})
    assert bad.status_code == 422

    db.tables["items"].append({"id": "i1", "sender_email": "johndoe@u.edu", "summary": "call 0300-1234567", "status": "searching"})
    row = c.get("/items").json()[0]
    assert row["sender_email"] == "jo***@u.edu" and "1234567" not in row["summary"]
    assert c.patch("/items/i1/resolve").json()["status"] == "updated"
    assert c.patch("/items/nope/resolve").status_code == 404


def test_webhook_secret(monkeypatch):
    monkeypatch.setattr(api.config, "WEBHOOK_SECRET", "s3cret")
    r = TestClient(api.app).post("/webhook/email", json={"subject": "a", "body": "b", "sender": "a@u.edu", "message_id": "1"})
    assert r.status_code == 401


def test_worker_marks_done_and_gives_up_on_poison(monkeypatch):
    marked = []
    emails = [{"uid": "1", "message_id": "m1", "sender": "a@u.edu", "subject": "s", "body": "b"}]
    monkeypatch.setattr(worker, "fetch_unread_emails", lambda: emails)
    monkeypatch.setattr(worker, "mark_as_seen", lambda uids: marked.append(list(uids)))
    monkeypatch.setattr(worker, "handle_email", lambda rec: (_ for _ in ()).throw(RuntimeError("LLM down")))
    worker._failures.clear()
    for _ in range(3):
        worker.run_once()
    assert marked == [[], [], ["1"]]  # kept unread twice, then given up on
