# Qatar Offers — local extraction + hybrid categorization + premium frontend

A static website plus a Python collector. GitHub Actions runs the collector
every six hours and republishes the site with GitHub Pages. The project is
kept portable so the same Python collector can later run on your own server.

## The frontend (web/)

`web/` is a multi-page static site. There is no separate server API — the
pages read `web/offers.json` and `web/malls.json` directly, which is what
`crawler/run.py` writes. That is "the backend" for this architecture.

- `index.html` — hero, live search, categories, featured/trending/latest
  rails, a filterable + sortable + paginated full browse grid, favorites,
  and a device profile box.
- `offer.html?id=…` — offer detail: price, promo code (with copy button),
  expiry progress bar, terms note, confidence note, source link, share,
  related offers, and `schema.org/Offer` JSON-LD for SEO.
- `merchant.html` (no query) — merchant index; `merchant.html?name=…` — a
  single merchant's profile and live offers.
- `admin.html` — a lightweight passphrase-gated dashboard (passphrase
  `qatar-offers-admin`, change it in `web/admin.html`) showing **real**
  analytics computed from the current `offers.json`: live offer count,
  needs-review count, offers-by-category/mall, AI-vs-rule classification
  split, average confidence, offers expiring soon, the last run's fetch
  errors, a full sortable offers table, and a "export flagged offers" CSV
  download. This gate is a convenience for a static site, not a secure
  backend login — anyone with the passphrase and the device can view it.
- `assets/app.css` / `assets/app.js` — shared design system and app logic:
  the 16-category taxonomy, English/Arabic (RTL) i18n, dark mode, search/
  filter/sort/pagination, favorites + recently-viewed + device profile
  (all `localStorage`, per-device — this static site has no multi-device
  user-account backend), share (native share sheet or copy-link), and SEO
  helpers.

Offers are never shown as active past their `end_date`: `run.py` already
excludes expired offers from `offers.json`, and the frontend re-checks the
date client-side as a second safety net before rendering anything.

All of this was verified with real browser automation (Playwright) against
data produced by the actual crawler — desktop/mobile, English/Arabic, light/
dark, search+filter+sort+pagination, favorites persistence, offer detail
actions, merchant navigation, the admin dashboard and CSV export, empty and
error states, mobile nav, and keyboard tab order.

## What's in the engine

- **Fetching**: `crawler/run.py` visits only the URLs explicitly listed in
  `sources.json` (and their configured sitemaps), with automatic retries
  (exponential backoff, 3 attempts by default) and per-run error logging to
  `data/run.log`. A page/image that fails to fetch is simply skipped for
  that run — it is never marked expired or deleted because of a temporary
  network problem. Unchanged pages and already-read images are skipped
  entirely (hash/URL cache in `data/state.json`), so a normal run only does
  network and extraction work for things that actually changed.
- **Extraction**: `crawler/ai.py` pulls titles, store names, descriptions,
  discount text, promo codes, prices (QAR), short product mentions, a
  terms-apply flag, start/end dates, and the source URL from page text, plus
  OCR'd promotion banners (local Tesseract, nothing uploaded anywhere).
  Nothing is invented — fields the page doesn't state are left `null`.
- **Categorization**: `crawler/categorize.py` is a two-tier classifier.
  1. A transparent weighted-keyword rule engine scores every offer against
     16 categories (Electronics, Fashion, Groceries, Restaurants, Travel,
     Technology, Beauty, Entertainment, Automotive, Home, Telecom, Banking,
     Education, Retail, Services, Other), each with subcategories, using the
     *whole* offer text — title, description, discount text — not just the
     merchant name (a merchant-name match alone is capped and can never push
     an offer to "confident" by itself).
  2. Offers the rule tier isn't confident about are optionally escalated to
     the Anthropic API for a second opinion — only if `ANTHROPIC_API_KEY` is
     set as a secret (see below). Each distinct offer is classified at most
     once ever: results are cached by content hash in `data/state.json`, and
     a per-run `AI_CALL_BUDGET` (default 40) hard-caps spend regardless of
     how many offers are found.
  A cross-cutting "Banking Offer" tag is applied whenever a bank card is
  mentioned (e.g. a restaurant discount that requires a specific bank's
  card stays categorized under Restaurants and is tagged Banking Offer,
  not re-categorized as Banking).
  Low-confidence results are published with `needs_review: true` and a
  numeric `category_confidence`, and the frontend shows a small "Under
  review" badge on them instead of silently guessing.
- **Deduplication**: offers are keyed by a content fingerprint (store +
  title + discount + end date), not by page URL, so the same offer appearing
  on more than one source page/sitemap entry updates one record (its
  `seen_sources` list grows) instead of creating duplicates.
- **Manual-correction protection**: setting `"locked_fields": ["category", ...]`
  on an offer record in `data/state.json` tells future automatic runs to
  keep that field exactly as a human last set it, even when the source page
  changes and the offer is re-extracted.
- **Safe migration**: `data/state.json` is versioned. Older state files are
  upgraded in place (new fields added, old lowercase category names mapped
  safely to `Other` + `needs_review: true` for re-check) — no offer records
  are ever dropped by the upgrade.
- **Timezone**: all "today", expiry comparisons, and "checked at" timestamps
  use Asia/Qatar (UTC+3, no DST), not UTC or server-local time.

## Setup on GitHub

1. Create a repository and upload the contents of this folder.
2. In repository **Settings → Pages**, choose **GitHub Actions** as the source.
3. (Optional) In **Settings → Secrets and variables → Actions**, add a
   secret named `ANTHROPIC_API_KEY` to enable the AI second-opinion tier for
   low-confidence categorizations. Without it, the collector runs fully
   locally/offline exactly as before — the rule tier handles everything.
4. Open **Actions → Refresh offers → Run workflow**.
5. When the workflow finishes, open the published GitHub Pages URL.

Scheduled refreshes run every six hours. GitHub is only being used as the
temporary runner/hosting location; `crawler/` can later be copied to a Linux
server and scheduled with cron or a system service.

## Add another mall

Edit `sources.json` and add a mall object with a unique `id`, English and
Arabic names, and official page URLs. Use `"type": "text"` for pages with
written promotion details and `"type": "images"` for pages whose offers are
banner images. For image pages, set `image_contains` to a URL fragment that
matches offer banners and, if helpful, `context_must` to text near promotion
images. Only use official public pages and respect each site's terms and
robots rules.

```json
{
  "id": "example-mall",
  "name": "Example Mall",
  "name_ar": "اسم المجمع",
  "area": "Doha",
  "pages": [
    {"url": "https://official.example.qa/offers", "type": "text"}
  ],
  "search": false
}
```

## Important limitations

- This is primarily a **local rule-based extraction/categorization engine**;
  the Anthropic API is only an optional, budget-capped second opinion for
  offers the rule tier flags as ambiguous. It can still miss unusual layouts
  or misclassify genuinely novel offer phrasing — that's exactly what
  `needs_review` is for.
- OCR depends on Tesseract and may struggle with stylized banners, small
  text or unusual fonts.
- Pages rendered entirely by JavaScript may not expose their offers to the
  basic HTTP crawler.
- A source registry cannot safely be exhaustive without checking each mall's
  official site and terms — the collector only publishes offers it can
  extract from configured sources; it never invents offers.
- Offers disappear when their stated end date has passed, or when no source
  has shown them for 10 days (`KEEP_DAYS` in `crawler/run.py`) — never
  because of a single failed fetch.

## Configuration (environment variables, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Enables AI second-opinion categorization for low-confidence offers. |
| `ANTHROPIC_CLASSIFY_MODEL` | `claude-haiku-4-5-20251001` | Model used for the optional AI tier. |
| `AI_CALL_BUDGET` | `40` | Max AI classification calls per run. |
| `AI_SLEEP` | `1.5` | Seconds to wait between fetches (politeness/rate limiting). |
| `FETCH_RETRIES` | `3` | Retry attempts per page/image fetch. |

## Test locally

Install Python 3.12 and the packages in `crawler/requirements.txt`. For
banner OCR, also install the Tesseract OCR system package and Arabic
language data. Run:

```bash
python crawler/test_run.py
```

This exercises extraction, the full category taxonomy (including the
bank-card-tag-vs-Banking-category case), promo code/price parsing, the
crawler end to end (including re-run deduplication), manual-correction
locking surviving an automatic refresh, and the retry/backoff wrapper.
