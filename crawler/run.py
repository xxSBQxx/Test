"""Fetch configured official mall pages and extract offers locally -> web/offers.json.
No external AI APIs are required; ANTHROPIC_API_KEY (optional) only escalates
offers the local classifier is unsure about. No search-engine APIs are used."""
import os, re, json, time, hashlib, pathlib, logging, datetime as dt
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import ai

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; QatarOffersBot/1.0)"}
KEEP_DAYS = 10        # an offer disappears if no source has shown it for this many days
MAX_NEW_IMAGES = 25   # per run; the rest are read on the next run
SLEEP = float(os.environ.get("AI_SLEEP", "1.5"))          # politeness delay between fetches
RETRIES = int(os.environ.get("FETCH_RETRIES", "3"))
AI_CALL_BUDGET = int(os.environ.get("AI_CALL_BUDGET", "40"))  # hard cap on AI classify calls/run
QATAR_TZ = dt.timezone(dt.timedelta(hours=3))             # Asia/Qatar has no DST
CATS = set(ai.categorize.TAXONOMY.keys())
STATE_VERSION = 2
# Fields a human reviewer may have hand-corrected. If a manual edit set
# "locked_fields" on an offer record, automatic refresh runs must not
# silently overwrite those specific fields.
LOCKABLE_FIELDS = {"category", "subcategory", "tags", "title", "description",
                    "discount_text", "promo_code", "price", "store_name"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(ROOT / "data/run.log"), logging.StreamHandler()],
)
log = logging.getLogger("qatar-offers")


def jload(p, d):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d

def jsave(p, o):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")

def today_qatar():
    return dt.datetime.now(QATAR_TZ).date()

def fetch(url, retries=RETRIES):
    """GET with exponential backoff. Raises only after all retries fail, so a
    transient error never looks the same as a confirmed 404/removed page to
    the caller -- callers skip the page for this run either way, but logging
    distinguishes the two cases."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < retries:
                wait = min(2 ** attempt, 20)
                log.warning("fetch retry %s/%s for %s in %ss (%s)", attempt, retries, url, wait, e)
                time.sleep(wait)
    log.error("fetch failed after %s attempts: %s (%s)", retries, url, last_exc)
    raise last_exc

def text_of(soup):
    for t in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        t.decompose()
    return re.sub(r"\n{2,}", "\n", soup.get_text("\n", strip=True))

def find_images(soup, base, spec):
    out, seen = [], set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if spec.get("image_contains", "/uploads/") not in src:
            continue
        url = urljoin(base, src)
        if url in seen:
            continue
        box = img.find_parent(["li", "article", "div"])
        ctx = box.get_text(" ", strip=True)[:250] if box else ""
        if spec.get("context_must") and spec["context_must"] not in ctx:
            continue
        seen.add(url); out.append((url, ctx))
    return out

def sitemap_urls(spec):
    """Best effort: newest pages of a sitemap whose address contains spec['contains']."""
    try:
        xml = fetch(spec["url"]).text
        for child in [u for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml) if u.endswith(".xml")][:5]:
            xml += fetch(child).text
        items = re.findall(r"<loc>\s*([^<]+?)\s*</loc>(?:\s*<lastmod>\s*([^<]+?)\s*</lastmod>)?", xml)
        items = [(u, m or "") for u, m in items if spec.get("contains", "") in u and not u.endswith(".xml")]
        return [u for u, _ in sorted(items, key=lambda x: x[1], reverse=True)[:8]]
    except Exception as e:
        log.warning("sitemap skipped: %s (%s)", spec.get("url"), e)
        return []

def clean_date(v):
    try:
        return dt.date.fromisoformat(v).isoformat() if isinstance(v, str) else None
    except ValueError:
        return None

def s300(v):
    return v.strip()[:300] if isinstance(v, str) and v.strip() else None

def fingerprint(o):
    """Content fingerprint used to detect the identical offer appearing on
    more than one page/source, independent of which URL it was seen on."""
    key = f"{o['store_name'].lower()}|{o['title'].lower()}|{(o.get('discount_text') or '').lower()}|{o['end_date']}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]

def normalize(o, today):
    if not isinstance(o, dict):
        return None
    store, title = s300(o.get("store_name")), s300(o.get("title"))
    if not store or not title:
        return None
    end, start = clean_date(o.get("end_date")), clean_date(o.get("start_date"))
    if end and end < today:
        return None
    if start and end and start > end:
        start = None
    url = o.get("source_url")
    products = o.get("products") if isinstance(o.get("products"), list) else []
    tags = o.get("tags") if isinstance(o.get("tags"), list) else []
    return {"store_name": store, "title": title, "title_ar": s300(o.get("title_ar")),
            "description": s300(o.get("description")), "discount_text": s300(o.get("discount_text")),
            "promo_code": s300(o.get("promo_code")), "price": s300(str(o["price"])) if o.get("price") else None,
            "products": [s300(p) for p in products if s300(p)][:5],
            "has_terms": bool(o.get("has_terms")),
            "category": o.get("category") if o.get("category") in CATS else "Other",
            "subcategory": s300(o.get("subcategory")) or "Uncategorized",
            "tags": sorted({s300(t) for t in tags if s300(t)}),
            "category_confidence": o.get("category_confidence") if isinstance(o.get("category_confidence"), (int, float)) else None,
            "needs_review": bool(o.get("needs_review")),
            "category_method": o.get("category_method") if o.get("category_method") in ("rule", "ai") else "rule",
            "start_date": start, "end_date": end, "language": s300(o.get("language")),
            "source_url": url if isinstance(url, str) and re.match(r"https?://", url) else None}

def add_offers(st, mall, offers, source_url, branch, today):
    ids = []
    for raw in offers:
        o = normalize(raw, today)
        if not o:
            continue
        if branch:
            o["description"] = ((o["description"] or "") + f" Branch: {branch}.").strip()
        fp = fingerprint(o)
        key = f"{mall['id']}|{fp}|{branch or ''}"
        i = hashlib.sha1(key.encode()).hexdigest()[:16]
        old = st["offers"].get(i)
        locked = set(old.get("locked_fields", [])) if old else set()
        merged = dict(o)
        if old:
            for field in locked & LOCKABLE_FIELDS:
                merged[field] = old.get(field, merged.get(field))
        # cross-source dedup: remember every source URL this exact offer was
        # seen on, instead of creating a second record for the same content.
        seen_sources = set(old.get("seen_sources", [])) if old else set()
        if o.get("source_url") or source_url:
            seen_sources.add(o.get("source_url") or source_url)
        st["offers"][i] = {**merged, "id": i, "mall_id": mall["id"], "mall_name": mall["name"],
                           "source_url": o["source_url"] or source_url, "seen_sources": sorted(seen_sources),
                           "origin": "local_extractor", "fingerprint": fp,
                           "locked_fields": sorted(locked),
                           "first_seen": old["first_seen"] if old else today, "last_seen": today}
        ids.append(i)
    return ids

def touch(st, ids, today):
    for i in ids:
        if i in st["offers"]:
            st["offers"][i]["last_seen"] = today

def migrate_state(st):
    """Upgrade an older state.json in place without losing any existing
    offer records. Only adds missing fields; never deletes data."""
    st.setdefault("version", 1)
    for k in ("pages", "images", "searched", "offers", "classifications"):
        st.setdefault(k, {})
    if st["version"] < 2:
        for o in st["offers"].values():
            o.setdefault("promo_code", None)
            o.setdefault("price", None)
            o.setdefault("products", [])
            o.setdefault("has_terms", False)
            o.setdefault("subcategory", "Uncategorized")
            o.setdefault("tags", [])
            o.setdefault("category_confidence", None)
            o.setdefault("needs_review", False)
            o.setdefault("category_method", "rule")
            o.setdefault("locked_fields", [])
            o.setdefault("seen_sources", [o["source_url"]] if o.get("source_url") else [])
            o.setdefault("fingerprint", fingerprint(o))
            # old "other"/lowercase categories -> new taxonomy default; never
            # invented, just safely bucketed for re-review.
            if o.get("category") not in CATS:
                o["category"] = "Other"
                o["needs_review"] = True
        st["version"] = STATE_VERSION
    return st

def main(root=ROOT):
    root = pathlib.Path(root)
    today = today_qatar()
    T = today.isoformat()
    cfg = jload(root / "sources.json", {"malls": []})
    st = migrate_state(jload(root / "data/state.json", {}))
    status, new_images, errors = [], 0, []
    now = dt.datetime.now(QATAR_TZ).strftime("%Y-%m-%d %H:%M AST")
    ai_budget = [AI_CALL_BUDGET]
    cache = st["classifications"]

    for mall in cfg["malls"]:
        pages = list(mall.get("pages", []))
        if mall.get("sitemap"):
            known = {p["url"] for p in pages}
            pages += [{"url": u, "type": "text"} for u in sitemap_urls(mall["sitemap"]) if u not in known]
        srcs = []
        for pg in pages:
            url = pg["url"]
            try:
                html = fetch(url).text
            except Exception as e:
                log.error("skip page %s: %s", url, e)
                errors.append({"mall": mall["id"], "url": url, "error": str(e)[:200]})
                continue
            srcs.append({"title": url.split("//")[-1][:60], "url": url})
            soup = BeautifulSoup(html, "html.parser")
            if pg.get("type") == "images":
                for img_url, ctx in find_images(soup, url, pg):
                    rec = st["images"].get(img_url)
                    if rec:                                  # already read before: no AI/OCR call
                        touch(st, rec["offer_ids"], T); continue
                    if new_images >= MAX_NEW_IMAGES:
                        continue
                    try:
                        r = fetch(img_url)
                    except Exception as e:
                        log.error("skip image %s: %s", img_url, e)
                        errors.append({"mall": mall["id"], "url": img_url, "error": str(e)[:200]})
                        continue
                    if len(r.content) > 6_000_000:
                        continue
                    mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0]
                    offers = ai.image_offers(r.content, mime, ctx, mall["name"], pg.get("branch"), T,
                                              cache=cache, ai_budget=ai_budget)
                    if offers is None:
                        continue                              # extraction failed: retry next run
                    st["images"][img_url] = {"offer_ids": add_offers(st, mall, offers, url, pg.get("branch"), T)}
                    new_images += 1
                    time.sleep(SLEEP)
            else:
                text = text_of(soup)
                h = hashlib.sha1(text.encode()).hexdigest()
                rec = st["pages"].get(url)
                if rec and rec["hash"] == h:                  # page unchanged: no re-extraction/AI call
                    touch(st, rec["offer_ids"], T); continue
                offers = ai.text_offers(text, mall["name"], url, T, cache=cache, ai_budget=ai_budget)
                if offers is None:
                    continue
                st["pages"][url] = {"hash": h, "offer_ids": add_offers(st, mall, offers, url, None, T)}
                time.sleep(SLEEP)
        status.append({"id": mall["id"], "checked_at": now, "sources": srcs[:10]})

    # Expiry/staleness cleanup. A page that merely failed to fetch this run
    # does NOT get its offers' last_seen bumped, so repeated failures age
    # toward the stale cutoff -- but a single transient failure never marks
    # anything expired on its own, and a confirmed end_date is the only way
    # an offer is removed immediately.
    for i, o in list(st["offers"].items()):
        ended = o.get("end_date") and o["end_date"] < T
        stale = (today - dt.date.fromisoformat(o["last_seen"])).days > KEEP_DAYS
        if ended or stale:
            del st["offers"][i]

    pub = ["id", "store_name", "mall_name", "title", "title_ar", "description", "discount_text",
           "promo_code", "price", "products", "has_terms",
           "category", "subcategory", "tags", "category_confidence", "needs_review",
           "start_date", "end_date", "source_url", "seen_sources", "language", "origin"]
    live = sorted(st["offers"].values(), key=lambda o: (o.get("end_date") or "9999", o["store_name"]))
    jsave(root / "web/offers.json", {
        "updated": now, "timezone": "Asia/Qatar", "status": status,
        "errors": errors[:20], "offers": [{k: o.get(k) for k in pub} for o in live],
    })
    jsave(root / "web/malls.json", [{k: m.get(k) for k in ("id", "name", "name_ar", "area")} for m in cfg["malls"]])
    jsave(root / "data/state.json", st)
    log.info("done: %s live offers, %s new images read, %s AI calls used, %s page/image errors",
              len(live), new_images, AI_CALL_BUDGET - ai_budget[0], len(errors))

if __name__ == "__main__":
    main()
