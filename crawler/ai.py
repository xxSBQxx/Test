"""Local, self-contained offer extraction engine.

No hosted AI, Gemini, or Google Search API keys are required to run. The
extractor itself is transparent Python rules (regex + heuristics) plus
optional local Tesseract OCR for promo banners (never uploaded anywhere).

Categorization (what category/subcategory/tags an extracted offer belongs
to) is handled separately in categorize.py: a weighted rule classifier that
reads the full offer, with an optional Anthropic API escalation for offers
it isn't confident about (see categorize.py and ANTHROPIC_API_KEY).
"""
import re
import datetime as dt
import categorize

OFFER_WORDS = re.compile(
    r"\b(offer|offers|promotion|promotions|sale|discount|off|deal|deals|"
    r"save|special price|buy\s*\d|free|clearance|mega sale|limited time|"
    r"خصم|عرض|عروض|تخفيضات|تخفيض|مجانا|مجاني|اشتر)\b", re.I
)
DISCOUNT = re.compile(
    r"(?:up to\s*)?\d{1,3}\s*%\s*(?:off|discount|خصم)?|"
    r"buy\s*\d+\s*(?:get|for)\s*\d+|buy one get one|bogo|"
    r"\b(?:buy one|get one|free|half price|save \d+)\b|"
    r"\d+\s*(?:QAR|QR|ر\.ق)\s*(?:off|خصم)?", re.I
)
PROMO_CODE = re.compile(r"\b(?:code|promo code|coupon code|use code)[:\s]+([A-Z0-9][A-Z0-9-]{2,19})\b", re.I)
PRICE = re.compile(r"\b(?:QAR|QR|ر\.ق)\s*([\d,]+(?:\.\d{1,2})?)\b|\b([\d,]+(?:\.\d{1,2})?)\s*(?:QAR|QR|ر\.ق)\b", re.I)
TERMS_HINT = re.compile(r"\b(terms?(?:\s*(?:and|&)\s*conditions?)?\s*apply|t&c[s]?\s*apply|conditions apply)\b", re.I)
DATE_PATTERNS = [
    # 19 Jul 2026 - 18 Oct 2026
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*(?:-|to|until|through|–|—)\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b", re.I),
    # 01/09/2026 - 31/12/2026 or 01-09-2026 - 31-12-2026
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(?:-|to|until|through|–|—)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b"),
]
MONTHS = {m.lower(): i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"],1)}
for name, num in list(MONTHS.items()):
    MONTHS[name[:3]] = num

def _date(s):
    s = s.strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None

def _dates(text):
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return _date(m.group(1)), _date(m.group(2))
    return None, None

def _promo_code(text):
    m = PROMO_CODE.search(text)
    return m.group(1).upper() if m else None

def _price(text):
    m = PRICE.search(text)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").replace(",", "") or None

def _products(text, store):
    """Pull out short product-like mentions near the offer text. Conservative:
    only short, title-cased or brand-adjacent phrases, never invented."""
    out, seen = [], set()
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*){0,3})\b", text):
        phrase = m.group(1).strip()
        low = phrase.lower()
        if low == (store or "").lower() or len(phrase) < 3 or len(phrase) > 40:
            continue
        if low in {"shop now", "learn more", "read more", "terms apply", "buy now"}:
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(phrase)
        if len(out) >= 5:
            break
    return out

def _store(text, fallback):
    # Prefer known brand/store names present in the candidate text.
    known = [
        "Carrefour","Lulu Hypermarket","Lulu","Monoprix","IKEA","Centrepoint","Max Fashion",
        "H&M","Zara","Mango","Nike","Adidas","Foot Locker","Sephora","Faces","Jarir",
        "Virgin Megastore","Samsung","Apple","iSpot","Fnac","Daiso","Miniso","Home Centre",
        "Bath & Body Works","Victoria's Secret","Marks & Spencer","M&S","LC Waikiki",
        "American Eagle","Bershka","Pull&Bear","Stradivarius","Massimo Dutti","R&B",
        "Al Meera","Toys R Us","Decathlon","Swarovski","Pandora","KFC","McDonald's",
        "Starbucks","Shake Shack","Tim Hortons","Pizza Hut","Chili's","Nando's"
    ]
    low = text.lower()
    for name in sorted(known, key=len, reverse=True):
        if name.lower() in low:
            return name
    # Use a short heading-like line before an offer keyword, excluding generic words.
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" -:|•")
        if 2 <= len(line) <= 48 and not OFFER_WORDS.search(line) and re.search(r"[A-Za-z]", line):
            if line.lower() not in {"promotions", "offers", "shop now", "learn more", "read more"}:
                return line
    return fallback

def _looks_like_heading(line):
    # A short, title-ish line with no offer/discount/promo/price language of
    # its own is likely a new store/section heading rather than part of the
    # current offer's supporting detail (code, price, dates).
    if PROMO_CODE.search(line) or PRICE.search(line) or any(p.search(line) for p in DATE_PATTERNS):
        return False
    return (2 <= len(line) <= 48 and not OFFER_WORDS.search(line) and not DISCOUNT.search(line)
            and re.match(r"^[A-Z0-9]", line))

def _candidate_chunks(text):
    # Web pages often flatten their text. Split around newlines and common separators,
    # then combine nearby lines so a store name and its offer remain together --
    # but stop at the next heading-like line in either direction so two
    # back-to-back store blocks never get merged into one offer.
    lines = [re.sub(r"\s+", " ", x).strip(" \t-•|") for x in text.splitlines()]
    lines = [x for x in lines if x]
    chunks = []
    for i, line in enumerate(lines):
        if OFFER_WORDS.search(line) or DISCOUNT.search(line):
            start = i
            if start > 0 and _looks_like_heading(lines[start - 1]):
                start -= 1  # include the immediate preceding store/heading line
            end = i + 1
            limit = min(len(lines), i + 3)
            while end < limit and not (end > i + 1 and _looks_like_heading(lines[end])):
                end += 1
            chunk = " ".join(lines[start:end])
            if chunk not in chunks:
                chunks.append(chunk)
    if not chunks and (OFFER_WORDS.search(text) or DISCOUNT.search(text)):
        chunks = [re.sub(r"\s+", " ", text)[:1000]]
    return chunks

def text_offers(text, mall, url, today, cache=None, ai_budget=None):
    found, seen = [], set()
    for chunk in _candidate_chunks(text):
        # Ignore navigation and generic statements that do not contain a concrete offer.
        disc = DISCOUNT.search(chunk)
        if not disc and not re.search(r"\b(sale|promotion|special offer|buy|free|clearance)\b", chunk, re.I):
            continue
        start, end = _dates(chunk)
        if end and end < today:
            continue
        title = next((x.strip() for x in chunk.split("  ") if x.strip()), chunk)
        title = re.sub(r"\s+", " ", title)[:180].strip(" -:|")
        if len(title) < 4:
            continue
        store = _store(chunk, "Mall promotion")
        # If the extracted "store" is the same as the title, use a safe generic label.
        if store.lower() == title.lower():
            store = "Mall promotion"
        discount = disc.group(0).strip() if disc else None
        description = chunk[:300]
        key = (store.lower(), title.lower(), end)
        if key in seen: continue
        seen.add(key)
        cls = categorize.classify(title, description, discount, store, cache=cache, ai_budget=ai_budget)
        found.append({
            "store_name": store, "title": title, "title_ar": None,
            "description": description, "discount_text": discount,
            "promo_code": _promo_code(chunk), "price": _price(chunk),
            "products": _products(chunk, store), "has_terms": bool(TERMS_HINT.search(chunk)),
            "category": cls["category"], "subcategory": cls["subcategory"], "tags": cls["tags"],
            "category_confidence": cls["confidence"], "needs_review": cls["needs_review"],
            "category_method": cls["method"],
            "start_date": start, "end_date": end,
            "language": "ar" if re.search(r"[\u0600-\u06ff]", chunk) else "en",
            "source_url": url
        })
    return found

def image_offers(data, mime, ctx, mall, branch, today, cache=None, ai_budget=None):
    """Run OCR locally if Tesseract is installed; never uploads the image."""
    try:
        from PIL import Image
        import pytesseract
        import io
        im = Image.open(io.BytesIO(data))
        extracted = pytesseract.image_to_string(im, lang="eng+ara")
    except Exception as exc:
        print("local OCR unavailable for banner:", str(exc)[:160])
        return []
    text = (ctx or "") + "\n" + extracted
    offers = text_offers(text, mall, "", today, cache=cache, ai_budget=ai_budget)
    for offer in offers:
        offer["description"] = ((offer.get("description") or "") + (f" Branch: {branch}." if branch else "")).strip()
    return offers
