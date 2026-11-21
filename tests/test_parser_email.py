from backend import ai_parser
from backend.email_listener import build_match_html, parse_raw_email


def test_normalize_valid():
    out = ai_parser.normalize_parsed({
        "is_lost_or_found": True, "intent": "FOUND", "item_name": "Hydro Flask",
        "category": "electronics ", "color": "", "location": "Student Union"})
    assert out["intent"] == "found" and out["category"] == "Electronics"
    assert out["color"] == "Unknown" and out["summary"]


def test_normalize_noise_and_bad_output():
    assert ai_parser.normalize_parsed({"is_lost_or_found": False}) == {"is_lost_or_found": False}
    assert not ai_parser.normalize_parsed("garbage")["is_lost_or_found"]
    assert not ai_parser.normalize_parsed({"is_lost_or_found": True, "intent": "maybe", "item_name": "x"})["is_lost_or_found"]
    assert not ai_parser.normalize_parsed({"is_lost_or_found": True, "intent": "lost", "item_name": ""})["is_lost_or_found"]


def test_unknown_category_becomes_other():
    out = ai_parser.normalize_parsed({"is_lost_or_found": True, "intent": "lost", "item_name": "Guitar", "category": "Music"})
    assert out["category"] == "Other"


def test_parse_raw_email_html_and_sender():
    raw = (b"From: Ali Khan <ali@uni.edu>\r\nSubject: Lost keys\r\nMessage-ID: <abc@x>\r\n"
           b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>Lost <b>keys</b> in library</p>")
    rec = parse_raw_email(raw, "7")
    assert rec["sender"] == "ali@uni.edu" and rec["message_id"] == "<abc@x>"
    assert "Lost keys in library" in rec["body"]


def test_html_in_email_is_escaped():
    html = build_match_html("<script>x</script>", "a & b", "evil@x.com", 0.9)
    assert "<script>" not in html and "&lt;script&gt;" in html
