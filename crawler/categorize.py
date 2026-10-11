"""Offer categorization engine.

Two tiers, used together so AI calls stay minimal:
 1. A transparent, weighted keyword/rule classifier runs on every offer first.
    It scores every supported category (not just merchant name) using the
    offer's title, description, discount text and store name, and returns a
    confidence score plus the runner-up margin.
 2. Only offers the rule tier is NOT confident about are optionally escalated
    to the Anthropic API (if ANTHROPIC_API_KEY is set) for a second opinion.
    Results are cached by content hash in data/state.json so the same offer
    text is never classified twice, and AI is skipped entirely with no key.

Never classifies solely from the merchant name: store-name matches are one
signal among several and are deliberately capped so they cannot alone push an
offer to "confident" status (e.g. a bank card perk at a restaurant stays
Restaurants + Banking Offer tag, not Banking, purely from store context).
"""
import os
import re
import json
import hashlib
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Taxonomy: category -> (subcategories, keyword weights)
# Keywords are matched as whole words/phrases against lower-cased text.
# ---------------------------------------------------------------------------
TAXONOMY = {
    "Electronics": {
        "subcategories": ["Mobile Phones", "Laptops & Computers", "TVs & Audio", "Home Appliances", "Gaming", "Accessories"],
        "keywords": {
            "phone": 2, "smartphone": 3, "iphone": 3, "laptop": 3, "tablet": 2, "macbook": 3,
            "tv": 2, "television": 3, "headphone": 2, "earbuds": 2, "speaker": 2, "camera": 2,
            "console": 2, "playstation": 3, "xbox": 3, "nintendo": 3, "appliance": 2,
            "refrigerator": 3, "washing machine": 3, "air conditioner": 2, "gadget": 2,
            "electronics": 3, "samsung": 2, "sony": 2, "lg": 2, "huawei": 2, "xiaomi": 2,
        },
    },
    "Technology": {
        "subcategories": ["Software", "IT Services", "Apps & Subscriptions", "Smart Home"],
        "keywords": {
            "software": 3, "app subscription": 3, "cloud storage": 3, "saas": 3,
            "smart home": 3, "it services": 3, "tech support": 2, "subscription plan": 2,
            "antivirus": 2, "vpn": 2, "coding bootcamp": 2,
        },
    },
    "Fashion": {
        "subcategories": ["Clothing", "Footwear", "Accessories", "Jewelry", "Kids Fashion"],
        "keywords": {
            "fashion": 3, "clothing": 3, "apparel": 3, "dress": 2, "shoes": 2, "sneaker": 2,
            "handbag": 2, "jewelry": 2, "jewellery": 2, "watch": 1, "sunglasses": 2,
            "zara": 2, "nike": 2, "adidas": 2, "h&m": 2, "mango": 2, "bershka": 2,
            "pull&bear": 2, "stradivarius": 2, "massimo dutti": 2, "lc waikiki": 2,
            "american eagle": 2, "swarovski": 2, "pandora": 2, "centrepoint": 2,
            "max fashion": 2, "marks & spencer": 2, "m&s": 2, "victoria's secret": 2,
        },
    },
    "Groceries": {
        "subcategories": ["Supermarket", "Fresh Produce", "Household Essentials"],
        "keywords": {
            "grocery": 3, "groceries": 3, "supermarket": 3, "hypermarket": 3, "fresh produce": 2,
            "carrefour": 2, "lulu": 2, "monoprix": 2, "al meera": 2, "household essentials": 2,
        },
    },
    "Restaurants": {
        "subcategories": ["Dining", "Cafes & Coffee", "Fast Food", "Delivery"],
        "keywords": {
            "restaurant": 3, "cafe": 2, "coffee": 2, "dining": 2, "menu": 2, "buffet": 2,
            "burger": 2, "pizza": 2, "kfc": 2, "mcdonald's": 2, "mcdonalds": 2, "starbucks": 2,
            "shake shack": 2, "tim hortons": 2, "pizza hut": 2, "chili's": 2, "nando's": 2,
            "food delivery": 2, "meal": 1, "brunch": 2,
        },
    },
    "Travel": {
        "subcategories": ["Flights", "Hotels", "Tour Packages", "Car Rental"],
        "keywords": {
            "flight": 3, "airline": 3, "hotel": 3, "resort": 2, "travel package": 3,
            "tour": 2, "vacation": 2, "holiday package": 2, "car rental": 3, "booking.com": 2,
            "qatar airways": 3, "visa package": 1,
        },
    },
    "Beauty": {
        "subcategories": ["Skincare", "Makeup", "Fragrance", "Salon & Spa"],
        "keywords": {
            "beauty": 3, "perfume": 3, "fragrance": 2, "cosmetic": 3, "skincare": 3,
            "makeup": 3, "salon": 2, "spa": 2, "sephora": 2, "faces": 2, "bath & body works": 2,
        },
    },
    "Entertainment": {
        "subcategories": ["Cinema", "Theme Parks", "Events", "Streaming"],
        "keywords": {
            "cinema": 3, "movie": 2, "theme park": 3, "amusement": 2, "concert": 2,
            "event ticket": 2, "streaming": 2, "vox cinemas": 2, "angry birds world": 2,
        },
    },
    "Automotive": {
        "subcategories": ["Car Service", "Spare Parts", "New Cars", "Tyres"],
        "keywords": {
            "car service": 3, "spare parts": 3, "tyre": 2, "tire": 2, "oil change": 2,
            "car wash": 2, "vehicle": 2, "automotive": 3, "showroom": 1, "toyota": 2, "nissan": 2,
        },
    },
    "Home": {
        "subcategories": ["Furniture", "Decor", "Kitchenware", "DIY & Hardware"],
        "keywords": {
            "furniture": 3, "home decor": 3, "mattress": 2, "kitchenware": 2, "ikea": 2,
            "home centre": 2, "decathlon": 1, "daiso": 1, "miniso": 1,
        },
    },
    "Telecom": {
        "subcategories": ["Mobile Plans", "Internet Packages", "Roaming"],
        "keywords": {
            "ooredoo": 3, "vodafone": 3, "sim card": 3, "data plan": 3, "roaming": 3,
            "broadband": 2, "fibernet": 2, "telecom": 3, "postpaid": 2, "prepaid": 2,
        },
    },
    "Banking": {
        "subcategories": ["Credit Card Offer", "Cashback", "Installments", "Loan Promotion"],
        "keywords": {
            "cashback": 3, "credit card offer": 3, "installment plan": 2, "0% installment": 3,
            "qnb": 2, "doha bank": 2, "commercial bank": 2, "cbq": 1, "qib": 2,
            "masraf al rayan": 2, "dukhan bank": 2, "al ahli bank": 2, "hsbc": 2,
            "standard chartered": 2, "ahlibank": 2, "qatar islamic bank": 2,
        },
    },
    "Education": {
        "subcategories": ["Courses", "Books & Stationery", "Tuition"],
        "keywords": {
            "course": 2, "tuition": 3, "school supplies": 3, "stationery": 2, "bookstore": 2,
            "jarir": 1, "learning": 1, "enrollment": 2, "academy": 2,
        },
    },
    "Retail": {
        "subcategories": ["Department Store", "Multi-category", "Clearance"],
        "keywords": {
            "department store": 3, "clearance sale": 2, "mega sale": 1, "multi-brand": 2,
            "centrepoint": 1, "lifestyle store": 2,
        },
    },
    "Services": {
        "subcategories": ["Health & Wellness", "Cleaning", "Repairs", "Photography"],
        "keywords": {
            "service offer": 2, "cleaning service": 3, "repair service": 3, "clinic": 2,
            "dental": 2, "fitness": 2, "gym membership": 3, "photography": 2, "laundry": 2,
        },
    },
    "Other": {"subcategories": ["Uncategorized"], "keywords": {}},
}

# A bank-card requirement is a cross-cutting TAG, not a category on its own,
# unless the offer *is* the banking product itself.
BANK_TAG_PATTERN = re.compile(
    r"\b(qnb|doha bank|commercial bank|cbq|qib|masraf al rayan|dukhan bank|al ahli bank|"
    r"hsbc|standard chartered|ahlibank|qatar islamic bank|credit card|debit card|bank card)\b",
    re.I,
)

CONFIDENT_MARGIN = 2   # top score must beat runner-up by this much
CONFIDENT_SCORE = 3    # and reach at least this absolute score

_WORD = re.compile(r"[a-z0-9&'%]+")


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower())


def rule_classify(title, description, discount_text, store_name):
    """Weighted keyword scoring across the full offer content (not just the
    merchant name). Returns category, subcategory, tags, confidence (0-1),
    method, and whether it needs human review."""
    body = _norm(" ".join(filter(None, [title, description, discount_text])))
    store = _norm(store_name)
    scores = {}
    for cat, spec in TAXONOMY.items():
        if cat == "Other":
            continue
        s = 0
        for kw, weight in spec["keywords"].items():
            if kw in body:
                s += weight
            # Store-name signal is capped low so merchant name alone can
            # never push a category to "confident" on its own.
            elif kw in store:
                s += min(weight, 1)
        if s:
            scores[cat] = s

    tags = []
    if BANK_TAG_PATTERN.search(body):
        tags.append("Banking Offer")

    if not scores:
        return {
            "category": "Other", "subcategory": "Uncategorized", "tags": tags,
            "confidence": 0.15, "method": "rule", "needs_review": True,
        }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_cat, top_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0
    confident = top_score >= CONFIDENT_SCORE and (top_score - runner_score) >= CONFIDENT_MARGIN

    # An offer that is itself a bank product (cashback/installment language
    # scored highest) stays Banking; a bank-card perk at another merchant
    # (e.g. a restaurant) keeps its real category and gets tagged instead.
    if top_cat == "Banking" and "Banking Offer" not in tags:
        tags.append("Banking Offer")

    # pick the strongest matching subcategory keyword as a hint, else first
    sub = TAXONOMY[top_cat]["subcategories"][0]
    for kw in TAXONOMY[top_cat]["keywords"]:
        if kw in body:
            for cand in TAXONOMY[top_cat]["subcategories"]:
                if any(w in cand.lower() for w in kw.split()):
                    sub = cand
                    break
            break

    confidence = min(0.5 + 0.08 * (top_score - runner_score), 0.95) if confident else min(0.3 + 0.05 * top_score, 0.55)
    return {
        "category": top_cat, "subcategory": sub, "tags": tags,
        "confidence": round(confidence, 2), "method": "rule",
        "needs_review": not confident,
    }


ALLOWED_CATS = set(TAXONOMY.keys())


def _ai_classify(title, description, discount_text, store_name, model, api_key):
    """Single Anthropic Messages API call. Returns a dict or None on any
    failure (never raises) so the caller always has the rule-based result to
    fall back on."""
    prompt = (
        "Classify this retail offer. Read the whole offer, not just the merchant "
        "name (e.g. a restaurant discount that requires a bank card belongs under "
        "Restaurants, tagged Banking Offer, not under Banking).\n"
        f"Store: {store_name}\nTitle: {title}\nDescription: {description}\nDiscount: {discount_text}\n\n"
        "Allowed categories: " + ", ".join(sorted(ALLOWED_CATS)) + ".\n"
        "Respond with ONLY compact JSON: "
        '{"category":"...","subcategory":"...","tags":["..."],"confidence":0.0}'
    )
    body = json.dumps({
        "model": model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
        parsed = json.loads(text)
        cat = parsed.get("category")
        if cat not in ALLOWED_CATS:
            return None
        sub = parsed.get("subcategory") or TAXONOMY[cat]["subcategories"][0]
        tags = parsed.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        conf = float(parsed.get("confidence", 0.7))
        conf = max(0.0, min(conf, 1.0))
        return {
            "category": cat, "subcategory": str(sub)[:60], "tags": [str(t)[:40] for t in tags][:5],
            "confidence": round(conf, 2), "method": "ai", "needs_review": conf < 0.5,
        }
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
        return None
    except Exception:
        return None


def classify(title, description, discount_text, store_name, cache=None, ai_budget=None):
    """Main entry point. `cache` is a dict (state['classifications']) keyed by
    content hash so identical offer text is classified at most once, ever.
    `ai_budget` is a mutable [int] counter; decremented on each AI call made,
    so a single run can cap total AI spend regardless of offer count."""
    body_key = _norm(" ".join(filter(None, [store_name, title, description, discount_text])))
    content_hash = hashlib.sha1(body_key.encode("utf-8")).hexdigest()[:20]

    if cache is not None and content_hash in cache:
        return cache[content_hash]

    result = rule_classify(title, description, discount_text, store_name)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_CLASSIFY_MODEL", "claude-haiku-4-5-20251001")
    if result["needs_review"] and api_key and (ai_budget is None or ai_budget[0] > 0):
        ai_result = _ai_classify(title, description, discount_text, store_name, model, api_key)
        if ai_budget is not None:
            ai_budget[0] -= 1
        if ai_result:
            # Merge: AI's tags augment (never silently drop) the bank tag the
            # rule tier already found from explicit keyword evidence.
            merged_tags = sorted(set(result["tags"]) | set(ai_result["tags"]))
            ai_result["tags"] = merged_tags
            result = ai_result

    if cache is not None:
        cache[content_hash] = result
    return result
