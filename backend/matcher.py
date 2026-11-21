"""Store an item, search for an opposite-intent match, and notify both people."""
from backend.ai_parser import generate_embedding
from backend.config import config
from backend.db import get_supabase
from backend.email_listener import send_match_notification
from backend.utils import log


def is_duplicate(message_id: str) -> bool:
    rows = get_supabase().table("items").select("id").eq("message_id", message_id).limit(1).execute().data
    return bool(rows)


def category_ok(a: str, b: str) -> bool:
    """Categories must agree, unless one side is the vague 'Other'."""
    a, b = (a or "").lower(), (b or "").lower()
    return a == b or "other" in (a, b)


def build_embedding_text(item: dict) -> str:
    parts = [item["intent"], item["item_name"], item["category"], item["color"],
             item["brand"], item["location"], item["summary"]]
    return " | ".join(str(p) for p in parts if p and str(p) != "Unknown")


def process_and_match_item(item_data: dict, sender_email: str, message_id: str,
                           send_emails: bool = True) -> dict:
    """Returns {"status": "duplicate" | "stored" | "matched", "item_id": ..., "match": {...}|None}."""
    db = get_supabase()

    if is_duplicate(message_id):
        log.info("Skipping duplicate message %s", message_id)
        return {"status": "duplicate", "item_id": None, "match": None}

    embedding = generate_embedding(build_embedding_text(item_data))

    new_item = {
        "message_id": message_id,
        "sender_email": sender_email,
        "intent": item_data["intent"],
        "item_name": item_data["item_name"],
        "category": item_data["category"],
        "color": item_data["color"],
        "brand": item_data["brand"],
        "location": item_data["location"],
        "event_date_time": item_data["event_date_time"],
        "summary": item_data["summary"],
        "embedding": embedding,
        "status": "searching",
    }
    item_id = db.table("items").insert(new_item).execute().data[0]["id"]

    opposite = "found" if item_data["intent"] == "lost" else "lost"
    candidates = db.rpc("match_items", {
        "query_embedding": embedding,
        "match_intent": opposite,
        "match_threshold": config.MATCH_THRESHOLD,
        "max_results": 5,
    }).execute().data or []

    for cand in candidates:
        if cand["sender_email"] == sender_email:      # never match someone with themselves
            continue
        if not category_ok(item_data["category"], cand["category"]):
            continue

        # Claim the candidate. If another worker grabbed it first, this updates 0 rows.
        claimed = (db.table("items").update({"status": "matched"})
                   .eq("id", cand["id"]).eq("status", "searching").execute().data)
        if not claimed:
            continue
        db.table("items").update({"status": "matched"}).eq("id", item_id).execute()

        lost_id, found_id = (item_id, cand["id"]) if item_data["intent"] == "lost" else (cand["id"], item_id)
        match_row = db.table("matches").insert({
            "lost_item_id": lost_id, "found_item_id": found_id,
            "similarity_score": cand["similarity"], "notified": False,
        }).execute().data[0]

        if send_emails:
            ok_new = send_match_notification(sender_email, item_data["item_name"], cand["summary"],
                                             cand["sender_email"], cand["similarity"])
            ok_old = send_match_notification(cand["sender_email"], cand["item_name"], item_data["summary"],
                                             sender_email, cand["similarity"])
            if ok_new and ok_old:
                db.table("matches").update({"notified": True}).eq("id", match_row["id"]).execute()

        log.info("Matched %s <-> %s (%.3f)", lost_id, found_id, cand["similarity"])
        return {"status": "matched", "item_id": item_id,
                "match": {"match_id": match_row["id"], "item_name": cand["item_name"],
                          "similarity": cand["similarity"]}}

    return {"status": "stored", "item_id": item_id, "match": None}
