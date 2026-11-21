from backend import utils


def test_parse_sender():
    assert utils.parse_sender("Ali Khan <Ali@Uni.edu>") == "ali@uni.edu"
    assert utils.parse_sender("no address here") == ""


def test_mask_email():
    assert utils.mask_email("johndoe@uni.edu") == "jo***@uni.edu"
    assert utils.mask_email("not-an-email") == "not-an-email"


def test_redact_phones():
    out = utils.redact_phones("call me on +92 300 1234567 or 0300-1234567, room 12")
    assert "1234567" not in out and "room 12" in out


def test_retry_backs_off_then_succeeds(monkeypatch):
    monkeypatch.setattr(utils.time, "sleep", lambda s: None)
    calls = {"n": 0}

    @utils.retry(attempts=3, base_delay=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("rate limited")
        return "ok"

    assert flaky() == "ok" and calls["n"] == 3


def test_retry_gives_up(monkeypatch):
    monkeypatch.setattr(utils.time, "sleep", lambda s: None)

    @utils.retry(attempts=2, base_delay=0.01)
    def always_fails():
        raise RuntimeError("down")

    try:
        always_fails()
        assert False, "should have raised"
    except RuntimeError:
        pass
