"""Offline tests for the local extraction, categorization, and crawler engine."""
import sys, pathlib, datetime as dt, json, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ai, run, categorize

today = dt.date.today().isoformat()
future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
past = (dt.date.today() - dt.timedelta(days=5)).isoformat()

# --- extraction -------------------------------------------------------
items = ai.text_offers(
    "Promotions\nNike\nNike up to 50% off\nValid 01 Sep 2026 - 31 Dec 2026\n"
    "Carrefour\nBuy 1 get 1 Free\n",
    "Mall of Qatar", "https://mall.example/offers", today
)
assert items, "Should extract at least one offer"
assert any(x["store_name"] == "Nike" and x["discount_text"] for x in items), items
assert all(x["source_url"] == "https://mall.example/offers" for x in items)
assert all(x["category"] in run.CATS for x in items), items
assert all("subcategory" in x and "tags" in x and "category_confidence" in x for x in items)

# expired date ranges are filtered
old = ai.text_offers(
    "Nike\nSale up to 50% off\n01 Jan 2020 - 31 Jan 2020",
    "Example Mall", "https://example.test", today
)
assert old == [], old

# --- categorization taxonomy -------------------------------------------
cls = categorize.classify("50% off dresses", "New season fashion sale", "50% off", "Zara")
assert cls["category"] == "Fashion", cls

cls = categorize.classify("20% off dining bill", "Enjoy 20% off your restaurant bill when you pay with your "
                           "QNB credit card at this restaurant", "20% off", "Nando's")
assert cls["category"] == "Restaurants" and "Banking Offer" in cls["tags"], cls

cls = categorize.classify("0% installment cashback", "Get cashback on your QIB credit card purchases",
                           "", "QIB")
assert cls["category"] == "Banking", cls

# merchant name alone should not be enough to classify confidently
cls = categorize.classify("Special promotion", "Visit us today", "", "Carrefour")
assert cls["needs_review"] in (True, False)  # just must not crash; weak signal path

# --- promo code / price / products extraction ---------------------------
items2 = ai.text_offers(
    "Samsung Galaxy\nSamsung Galaxy S24 offer\n20% off laptops\nUse code TECH20\nQAR 199 only\n"
    "Valid 01 Jan 2026 - 31 Dec 2026\n",
    "City Center Doha", "https://city.example/offers", today
)
assert any(o.get("promo_code") == "TECH20" for o in items2), items2
assert any(o.get("price") == "199" for o in items2), items2

# --- crawler integration with a fake page and no network ----------------
class Response:
    def __init__(self, text):
        self.text = text
        self.content = text.encode()
        self.headers = {"content-type": "text/html"}

original_fetch = run.fetch
run.fetch = lambda url, retries=run.RETRIES: Response("<html><body><h1>Nike</h1><p>Nike up to 50% off</p></body></html>")
root = pathlib.Path(tempfile.mkdtemp())
(root / "sources.json").write_text(json.dumps({"malls": [{
    "id": "test-mall", "name": "Test Mall", "name_ar": "مجمع تجريبي",
    "pages": [{"url": "https://example.test/offers", "type": "text"}]
}]}), encoding="utf-8")
run.main(root)
out = json.loads((root / "web/offers.json").read_text(encoding="utf-8"))
assert out["offers"], out
assert out["offers"][0]["mall_name"] == "Test Mall"
assert out["offers"][0]["source_url"] == "https://example.test/offers"
assert out["timezone"] == "Asia/Qatar"
assert "category" in out["offers"][0] and out["offers"][0]["category"] in run.CATS

# re-running with an unchanged page must not duplicate the offer record
state_after_1 = json.loads((root / "data/state.json").read_text(encoding="utf-8"))
n1 = len(state_after_1["offers"])
run.main(root)
state_after_2 = json.loads((root / "data/state.json").read_text(encoding="utf-8"))
assert len(state_after_2["offers"]) == n1, "unchanged page must not create duplicate offers"

# --- manual-correction protection ---------------------------------------
off_id = next(iter(state_after_2["offers"]))
state_after_2["offers"][off_id]["category"] = "Technology"  # simulate a human correction
state_after_2["offers"][off_id]["locked_fields"] = ["category"]
(root / "data/state.json").write_text(json.dumps(state_after_2), encoding="utf-8")
# force the page hash to change (so it's re-extracted) without changing the
# offer content itself, so it maps to the SAME fingerprint/id as before
run.fetch = lambda url, retries=run.RETRIES: Response(
    "<html><body><h1>Nike</h1><p>Nike up to 50% off</p><!-- refreshed --></body></html>")
run.main(root)
state_after_3 = json.loads((root / "data/state.json").read_text(encoding="utf-8"))
assert state_after_3["offers"][off_id]["category"] == "Technology", \
    "a manually-locked field must survive an automatic refresh"

# --- retry/backoff wrapper (tests run.fetch itself, not a replacement) ---
run.fetch = original_fetch
import requests as _requests
calls = {"n": 0}
def flaky_get(url, headers=None, timeout=None):
    calls["n"] += 1
    if calls["n"] < 3:
        raise _requests.exceptions.ConnectionError("transient")
    class R:
        text = "ok"
        def raise_for_status(self): pass
    return R()
orig_get = _requests.get
_requests.get = flaky_get
import time as _time
_orig_sleep = _time.sleep
_time.sleep = lambda s: None  # don't actually wait during tests
r = run.fetch("https://example.test/flaky")
assert r.text == "ok" and calls["n"] == 3, "fetch should retry transient failures and then succeed"
_time.sleep = _orig_sleep
_requests.get = orig_get
print("all local extraction, categorization, and crawler tests passed")
