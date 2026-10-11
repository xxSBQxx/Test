/* Qatar Offers — shared app module.
 * Connects directly to the real generated data files (web/offers.json,
 * web/malls.json) produced by crawler/run.py — there is no separate server
 * API in this project, so this IS "the backend" for a static GitHub Pages
 * deployment. No offer data is ever invented client-side.
 */
(function (global) {
  "use strict";

  const QATAR_TZ_OFFSET_MIN = 180; // Asia/Qatar, UTC+3, no DST
  const dayMs = 86400000;

  // ---- category taxonomy (mirrors crawler/categorize.py TAXONOMY keys) ---
  const TAXONOMY = {
    Electronics: { ar: "إلكترونيات", icon: "chip" },
    Fashion: { ar: "أزياء", icon: "shirt" },
    Groceries: { ar: "بقالة", icon: "cart" },
    Restaurants: { ar: "مطاعم", icon: "cup" },
    Travel: { ar: "سفر", icon: "plane" },
    Technology: { ar: "تقنية", icon: "cloud" },
    Beauty: { ar: "جمال", icon: "sparkle" },
    Entertainment: { ar: "ترفيه", icon: "ticket" },
    Automotive: { ar: "سيارات", icon: "car" },
    Home: { ar: "منزل", icon: "home" },
    Telecom: { ar: "اتصالات", icon: "signal" },
    Banking: { ar: "بنوك", icon: "card" },
    Education: { ar: "تعليم", icon: "book" },
    Retail: { ar: "تجزئة", icon: "bag" },
    Services: { ar: "خدمات", icon: "tool" },
    Other: { ar: "أخرى", icon: "tag" },
  };
  const CAT_ORDER = Object.keys(TAXONOMY);

  const ICONS = {
    chip: '<path d="M8 2v3M16 2v3M8 19v3M16 19v3M2 8h3M2 16h3M19 8h3M19 16h3"/><rect x="7" y="7" width="10" height="10" rx="2"/>',
    shirt: '<path d="M8 3 4 6l1 4h2v11h10V10h2l1-4-4-3-3 2h-2z"/>',
    cart: '<circle cx="9" cy="20" r="1.3"/><circle cx="18" cy="20" r="1.3"/><path d="M2 3h2l2.4 12.2a2 2 0 0 0 2 1.6h8.4a2 2 0 0 0 2-1.6L21 7H6"/>',
    cup: '<path d="M4 3h13v9a6 6 0 0 1-6 6H8a4 4 0 0 1-4-4V3Z"/><path d="M17 7h2a2 2 0 0 1 0 6h-2"/><path d="M8 1v2M12 1v2M4 21h11"/>',
    plane: '<path d="M2 16 22 8 20 6 10 10 4 9 2 11l5 3-1 5 2-1 2-4 6 3-1-9z"/>',
    cloud: '<path d="M7 18a4.5 4.5 0 0 1-.6-8.97A5.5 5.5 0 0 1 17.3 8.1 4 4 0 0 1 17 18H7Z"/>',
    sparkle: '<path d="M12 2l1.8 5.6L19 9l-5.2 1.9L12 16l-1.8-5.1L5 9l5.2-1.4L12 2Z"/><circle cx="19" cy="18" r="1.6"/>',
    ticket: '<path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4Z"/><path d="M10 7v10" stroke-dasharray="2 2"/>',
    car: '<path d="M3 16V12l2-5h12l3 5v4"/><path d="M3 16h18M7 16v2M17 16v2"/><circle cx="7" cy="16" r="1.6"/><circle cx="17" cy="16" r="1.6"/>',
    home: '<path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
    signal: '<path d="M4 20h2v-4H4zM9 20h2V11H9zM14 20h2V7h-2zM19 20h2V3h-2z"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/><path d="M6 15h4"/>',
    book: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5Z"/><path d="M4 19.5V4.5"/>',
    bag: '<path d="M6 7h12l1 14H5zM9 7a3 3 0 0 1 6 0"/>',
    tool: '<path d="m14.5 6.5 3 3L7 20H4v-3L14.5 6.5Z"/><path d="M13 5l6 6M18 2l4 4-3 3-4-4z"/>',
    tag: '<path d="M3 11.5 11.5 3H19a2 2 0 0 1 2 2v7.5L12.5 21 3 11.5Z"/><circle cx="14.5" cy="8.5" r="1.4"/>',
  };
  function iconSvg(name, cls) {
    return `<svg class="${cls || "ic"}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.tag}</svg>`;
  }

  // ---------------------------------------------------------------- i18n --
  const DICT = {
    en: {
      dir: "ltr", app: "Qatar Offers", tagline: "Real, verified deals from malls across Qatar — refreshed automatically.",
      nav_home: "Home", nav_browse: "Browse", nav_favorites: "Favorites", nav_merchants: "Merchants", nav_admin: "Admin",
      search_ph: "Search offers, stores, categories…", search_btn: "Search",
      live_offers: "live offers", malls_tracked: "malls tracked", updated: "Last updated",
      live_offers_n: n => `${n} live offer${n === 1 ? "" : "s"}`,
      categories: "Categories", categories_sub: "Browse by what you're shopping for",
      featured: "Featured", featured_sub: "Verified, high-confidence offers", view_all: "View all",
      trending: "Trending stores", trending_sub: "Most active merchants right now",
      latest: "Latest offers", latest_sub: "Newest finds from official sources",
      browse_all: "All offers", sort: "Sort", sort_new: "Newest", sort_expiry: "Expiring soon",
      sort_az: "Store A–Z", sort_disc: "Biggest discount",
      filter_cat: "Category", filter_mall: "Mall", filter_all: "All", verified_only: "Verified only",
      has_promo: "Has promo code", clear_filters: "Clear filters",
      results: n => `${n} offer${n === 1 ? "" : "s"} found`,
      empty_title: "No offers match that search", empty_body: "Try a broader search or clear your filters.",
      error_title: "Couldn't load offers", error_body: "Check your connection and try again.", retry: "Retry",
      loading: "Loading offers…",
      days_left: "days left", today: "last day", no_end: "ongoing",
      verified: "Verified", review: "Needs review", bank_offer: "Banking Offer",
      close: "Close", share: "Share", share_copied: "Link copied to clipboard",
      save: "Save", saved: "Saved", unsave: "Remove from favorites",
      price: "Price", promo_code: "Promo code", copy: "Copy", copied: "Copied",
      starts: "Starts", ends: "Ends", source: "View official source", terms: "Terms",
      terms_note: "This offer mentions terms & conditions on the source page — confirm details with the store before you go.",
      related: "Related offers", at_store: "More from", back: "Back",
      breadcrumb_home: "Home", breadcrumb_browse: "Browse",
      merchants_title: "Merchants", merchants_sub: "Every store with a live offer right now",
      merchant_offers: n => `${n} live offer${n === 1 ? "" : "s"}`,
      favorites_title: "Your favorites", favorites_sub: "Saved on this device",
      favorites_empty_title: "No favorites yet", favorites_empty_body: "Tap the heart on any offer to save it here.",
      recently_viewed: "Recently viewed",
      confidence_note: n => `Categorized automatically (${n}% confidence). Flagged for human review if this looks wrong.`,
      source_tag: "Source", origin_note: "Extracted locally from the official source page.",
      admin_title: "Admin dashboard", admin_sub: "Live analytics computed from the current dataset",
      admin_gate_title: "Admin access", admin_gate_body: "This is a lightweight local gate for a static site — not a secured backend login. Anyone with the passphrase and this device can view the dashboard.",
      admin_gate_ph: "Enter passphrase", admin_gate_btn: "Enter", admin_gate_wrong: "Incorrect passphrase.",
      admin_logout: "Lock dashboard",
      kpi_live: "Live offers", kpi_review: "Needs review", kpi_malls: "Malls configured", kpi_errors: "Fetch errors (last run)",
      kpi_expiring: "Expiring in 3 days", kpi_ai: "AI-assisted", kpi_conf: "Avg. confidence",
      by_category: "Offers by category", by_mall: "Offers by mall", method_split: "Classification method",
      recent_errors: "Recent fetch errors", no_errors: "No fetch errors on the last run.",
      all_offers_table: "All live offers", th_offer: "Offer", th_store: "Store", th_mall: "Mall", th_cat: "Category",
      th_conf: "Confidence", th_ends: "Ends", th_status: "Status", export_csv: "Export flagged (CSV)",
      account_title: "Device profile", account_body: "Favorites and recently viewed are stored on this device only — this static site has no user-account backend, so nothing is synced across devices.",
      account_name_ph: "Display name (optional)", account_save: "Save",
      theme_toggle: "Toggle theme", lang_toggle: "العربية", menu: "Menu",
      skip: "Skip to content", search_label: "Search offers",
    },
    ar: {
      dir: "rtl", app: "عروض قطر", tagline: "عروض حقيقية وموثّقة من مجمعات قطر — تُحدَّث تلقائياً.",
      nav_home: "الرئيسية", nav_browse: "تصفح", nav_favorites: "المفضلة", nav_merchants: "المتاجر", nav_admin: "لوحة التحكم",
      search_ph: "ابحث عن عروض، متاجر، فئات…", search_btn: "بحث",
      live_offers: "عرض نشط", malls_tracked: "مجمع مُتابَع", updated: "آخر تحديث",
      live_offers_n: n => `${n} عرض نشط`,
      categories: "الفئات", categories_sub: "تصفح حسب ما تبحث عنه",
      featured: "مميزة", featured_sub: "عروض موثّقة بثقة عالية", view_all: "عرض الكل",
      trending: "متاجر رائجة", trending_sub: "الأكثر نشاطاً الآن",
      latest: "أحدث العروض", latest_sub: "أحدث ما تم رصده من المصادر الرسمية",
      browse_all: "كل العروض", sort: "ترتيب", sort_new: "الأحدث", sort_expiry: "الأقرب للانتهاء",
      sort_az: "المتجر أ-ي", sort_disc: "أعلى خصم",
      filter_cat: "الفئة", filter_mall: "المجمع", filter_all: "الكل", verified_only: "الموثّقة فقط",
      has_promo: "يحتوي كود خصم", clear_filters: "مسح الفلاتر",
      results: n => `${n} عرض`,
      empty_title: "لا توجد عروض مطابقة", empty_body: "جرّب بحثاً أوسع أو امسح الفلاتر.",
      error_title: "تعذّر تحميل العروض", error_body: "تحقق من الاتصال وحاول مرة أخرى.", retry: "إعادة المحاولة",
      loading: "جارٍ تحميل العروض…",
      days_left: "أيام متبقية", today: "آخر يوم", no_end: "بلا نهاية",
      verified: "موثّق", review: "قيد المراجعة", bank_offer: "عرض بنكي",
      close: "إغلاق", share: "مشاركة", share_copied: "تم نسخ الرابط",
      save: "حفظ", saved: "محفوظ", unsave: "إزالة من المفضلة",
      price: "السعر", promo_code: "رمز الخصم", copy: "نسخ", copied: "تم النسخ",
      starts: "يبدأ", ends: "ينتهي", source: "عرض المصدر الرسمي", terms: "الشروط",
      terms_note: "يذكر هذا العرض شروطاً وأحكاماً في الصفحة الرسمية — تأكد من التفاصيل مع المتجر قبل الذهاب.",
      related: "عروض ذات صلة", at_store: "المزيد من", back: "رجوع",
      breadcrumb_home: "الرئيسية", breadcrumb_browse: "تصفح",
      merchants_title: "المتاجر", merchants_sub: "كل متجر لديه عرض نشط الآن",
      merchant_offers: n => `${n} عرض نشط`,
      favorites_title: "مفضلتك", favorites_sub: "محفوظة على هذا الجهاز",
      favorites_empty_title: "لا توجد مفضلة بعد", favorites_empty_body: "اضغط على القلب في أي عرض لحفظه هنا.",
      recently_viewed: "شوهد مؤخراً",
      confidence_note: n => `صُنِّف تلقائياً بثقة ${n}%. يُراجَع يدوياً إن بدا غير دقيق.`,
      source_tag: "المصدر", origin_note: "استُخرج محلياً من صفحة المصدر الرسمية.",
      admin_title: "لوحة التحكم", admin_sub: "تحليلات حقيقية محسوبة من البيانات الحالية",
      admin_gate_title: "دخول لوحة التحكم", admin_gate_body: "هذه بوابة محلية بسيطة لموقع ثابت — وليست تسجيل دخول خادم آمن. أي شخص يملك كلمة المرور وهذا الجهاز يمكنه عرض اللوحة.",
      admin_gate_ph: "أدخل كلمة المرور", admin_gate_btn: "دخول", admin_gate_wrong: "كلمة المرور غير صحيحة.",
      admin_logout: "قفل اللوحة",
      kpi_live: "عروض نشطة", kpi_review: "قيد المراجعة", kpi_malls: "مجمعات مُهيّأة", kpi_errors: "أخطاء الجلب (آخر تشغيل)",
      kpi_expiring: "تنتهي خلال 3 أيام", kpi_ai: "بمساعدة الذكاء الاصطناعي", kpi_conf: "متوسط الثقة",
      by_category: "العروض حسب الفئة", by_mall: "العروض حسب المجمع", method_split: "طريقة التصنيف",
      recent_errors: "أخطاء الجلب الأخيرة", no_errors: "لا توجد أخطاء جلب في آخر تشغيل.",
      all_offers_table: "كل العروض النشطة", th_offer: "العرض", th_store: "المتجر", th_mall: "المجمع", th_cat: "الفئة",
      th_conf: "الثقة", th_ends: "ينتهي", th_status: "الحالة", export_csv: "تصدير المُعلَّمة (CSV)",
      account_title: "ملف الجهاز", account_body: "تُحفظ المفضلة والمُشاهَد مؤخراً على هذا الجهاز فقط — هذا الموقع الثابت لا يملك نظام حسابات مستخدمين، لذا لا تتم المزامنة بين الأجهزة.",
      account_name_ph: "اسم العرض (اختياري)", account_save: "حفظ",
      theme_toggle: "تبديل المظهر", lang_toggle: "English", menu: "القائمة",
      skip: "تخطَّ إلى المحتوى", search_label: "ابحث عن العروض",
    },
  };

  // --------------------------------------------------------------- state --
  function getLang() { return localStorage.getItem("qo_lang") || "en"; }
  function setLang(l) { try { localStorage.setItem("qo_lang", l); } catch (e) {} }
  function getTheme() { return localStorage.getItem("qo_theme") || ""; }
  function setTheme(t) { try { localStorage.setItem("qo_theme", t); } catch (e) {} }

  function t() { return DICT[getLang()]; }

  function applyHtmlLangDir() {
    const lang = getLang();
    document.documentElement.lang = lang;
    document.documentElement.dir = DICT[lang].dir;
    const theme = getTheme();
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
  }

  // ------------------------------------------------------------- storage --
  function lsGet(key, fallback) {
    try { const v = JSON.parse(localStorage.getItem(key)); return v == null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function lsSet(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} }

  const Favorites = {
    all() { return lsGet("qo_favorites", []); },
    has(id) { return this.all().includes(id); },
    toggle(id) {
      const list = this.all();
      const i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1); else list.unshift(id);
      lsSet("qo_favorites", list.slice(0, 300));
      return i < 0;
    },
    count() { return this.all().length; },
  };
  const Recents = {
    all() { return lsGet("qo_recent", []); },
    add(id) {
      const list = this.all().filter(x => x !== id);
      list.unshift(id);
      lsSet("qo_recent", list.slice(0, 16));
    },
  };
  const Profile = {
    get() { return lsGet("qo_profile", { name: "" }); },
    set(p) { lsSet("qo_profile", p); },
  };

  // --------------------------------------------------------------- utils --
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function qatarToday() {
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
    const qatarMs = utcMs + QATAR_TZ_OFFSET_MIN * 60000;
    const q = new Date(qatarMs);
    return new Date(q.getFullYear(), q.getMonth(), q.getDate());
  }
  function daysLeft(endIso) {
    if (!endIso) return null;
    const end = new Date(endIso + "T00:00:00");
    return Math.round((end - qatarToday()) / dayMs);
  }
  function fmtPrice(p) { return p == null ? "" : `${p} QAR`; }
  function debounce(fn, ms) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; }
  function slug(s) { return encodeURIComponent(String(s || "")); }
  function unslug(s) { try { return decodeURIComponent(s || ""); } catch (e) { return s || ""; } }
  function discountNum(txt) {
    if (!txt) return 0;
    const m = String(txt).match(/(\d{1,3})\s*%/);
    return m ? parseInt(m[1], 10) : 0;
  }

  // ----------------------------------------------------------- data load --
  let _cache = null;
  async function loadData() {
    if (_cache) return _cache;
    const [offersRes, mallsRes] = await Promise.all([
      fetch("offers.json", { cache: "no-store" }),
      fetch("malls.json", { cache: "no-store" }).catch(() => null),
    ]);
    if (!offersRes.ok) throw new Error("offers.json " + offersRes.status);
    const meta = await offersRes.json();
    const malls = mallsRes && mallsRes.ok ? await mallsRes.json() : [];
    const today = qatarToday();
    // Defensive client-side re-check: never render an offer whose end date
    // has passed, even if a stale cached copy of offers.json is served.
    const offers = (meta.offers || []).filter(o => !o.end_date || new Date(o.end_date + "T00:00:00") >= today);
    _cache = { meta, malls, offers };
    return _cache;
  }

  // ------------------------------------------------------------- render --
  function categoryLabel(cat) {
    const lang = getLang();
    const entry = TAXONOMY[cat] || TAXONOMY.Other;
    return lang === "ar" ? entry.ar : cat;
  }
  function categoryIcon(cat, cls) {
    const entry = TAXONOMY[cat] || TAXONOMY.Other;
    return iconSvg(entry.icon, cls);
  }

  function expiryBadge(o) {
    const d = daysLeft(o.end_date);
    const tr = t();
    if (d === null) return `<span class="offer-expiry">${tr.no_end}</span>`;
    if (d <= 0) return `<span class="offer-expiry soon">${tr.today}</span>`;
    return `<span class="offer-expiry ${d <= 3 ? "soon" : ""}">${d} ${tr.days_left}</span>`;
  }

  function offerMedia(o) {
    if (o.image) {
      return `<div class="offer-media"><img src="${esc(o.image)}" alt="" loading="lazy" referrerpolicy="no-referrer"></div>`;
    }
    return `<div class="offer-media"><div class="placeholder">${categoryIcon(o.category)}</div></div>`;
  }

  function offerTitle(o) {
    const lang = getLang();
    return lang === "ar" && o.title_ar ? o.title_ar : o.title;
  }

  function offerCard(o) {
    const tr = t();
    const fav = Favorites.has(o.id);
    const verified = !o.needs_review && (o.category_confidence == null || o.category_confidence >= 0.5);
    return `<a class="offer-card" href="offer.html?id=${slug(o.id)}" data-id="${esc(o.id)}">
      ${offerMedia(o)}
      ${o.discount_text ? `<span class="offer-disc">${esc(o.discount_text)}</span>` : ""}
      ${expiryBadge(o)}
      <button type="button" class="fav-btn ${fav ? "on" : ""}" data-fav="${esc(o.id)}" aria-pressed="${fav}" aria-label="${fav ? tr.unsave : tr.save}">
        <svg viewBox="0 0 24 24" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7.5-4.6-10-9.2C.3 8 2 4.5 5.6 4a5 5 0 0 1 6.4 2.3A5 5 0 0 1 18.4 4C22 4.5 23.7 8 22 11.8 19.5 16.4 12 21 12 21Z"/></svg>
      </button>
      <div class="offer-body">
        <div class="offer-store">${verified ? `<span class="verified">${iconSvg("sparkle", "ic")}${tr.verified}</span> · ` : ""}${esc(o.store_name)}${o.mall_name ? " · " + esc(o.mall_name) : ""}</div>
        <div class="offer-title">${esc(offerTitle(o))}</div>
        <div class="offer-meta-row">
          ${o.price ? `<span class="price-tag">${esc(fmtPrice(o.price))}</span>` : ""}
          <span class="tag-chip">${esc(categoryLabel(o.category))}</span>
          ${(o.tags || []).includes("Banking Offer") ? `<span class="tag-chip bank">${tr.bank_offer}</span>` : ""}
          ${o.needs_review ? `<span class="tag-chip review">${tr.review}</span>` : ""}
        </div>
      </div>
    </a>`;
  }

  function skeletonCards(n) {
    return Array.from({ length: n }).map(() => `<div class="skeleton skel-card" aria-hidden="true"></div>`).join("");
  }

  function emptyState(title, body) {
    return `<div class="empty-state">${iconSvg("tag", "")}<h3>${esc(title)}</h3><p>${esc(body)}</p></div>`;
  }
  function errorState(onRetryAttr) {
    const tr = t();
    return `<div class="error-state">${iconSvg("tool", "")}<h3>${tr.error_title}</h3><p>${tr.error_body}</p><button type="button" class="pill-btn" ${onRetryAttr}>${tr.retry}</button></div>`;
  }

  function paginate(items, page, perPage) {
    const total = items.length;
    const pages = Math.max(1, Math.ceil(total / perPage));
    const p = Math.min(Math.max(1, page), pages);
    return { slice: items.slice((p - 1) * perPage, p * perPage), page: p, pages, total };
  }
  function renderPagination(container, state, onChange) {
    const { page, pages } = state;
    if (pages <= 1) { container.innerHTML = ""; return; }
    let html = `<button type="button" data-p="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Previous">‹</button>`;
    const span = 1;
    for (let i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || Math.abs(i - page) <= span) {
        html += `<button type="button" data-p="${i}" aria-current="${i === page}">${i}</button>`;
      } else if (Math.abs(i - page) === span + 1) {
        html += `<span aria-hidden="true">…</span>`;
      }
    }
    html += `<button type="button" data-p="${page + 1}" ${page >= pages ? "disabled" : ""} aria-label="Next">›</button>`;
    container.innerHTML = html;
    container.querySelectorAll("button[data-p]").forEach(b => b.addEventListener("click", () => {
      const p = parseInt(b.dataset.p, 10);
      if (p >= 1 && p <= pages) onChange(p);
    }));
  }

  function toast(msg) {
    let el = document.getElementById("qo-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "qo-toast";
      el.className = "toast";
      el.innerHTML = `<div class="msg" role="status" aria-live="polite"></div>`;
      document.body.appendChild(el);
    }
    el.querySelector(".msg").textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2200);
  }

  async function shareOffer(o) {
    const url = new URL("offer.html?id=" + slug(o.id), location.href).toString();
    const text = `${o.store_name}: ${offerTitle(o)}${o.discount_text ? " — " + o.discount_text : ""}`;
    if (navigator.share) {
      try { await navigator.share({ title: t().app, text, url }); return; } catch (e) { /* cancelled */ return; }
    }
    try {
      await navigator.clipboard.writeText(url);
      toast(t().share_copied);
    } catch (e) {
      prompt(t().share, url);
    }
  }

  function wireFavButtons(root) {
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-fav]");
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      const id = b.dataset.fav;
      const nowOn = Favorites.toggle(id);
      b.classList.toggle("on", nowOn);
      b.setAttribute("aria-pressed", String(nowOn));
      updateFavCount();
    });
  }
  function updateFavCount() {
    document.querySelectorAll("[data-fav-count]").forEach(el => {
      const n = Favorites.count();
      el.textContent = n > 0 ? String(n) : "";
      el.hidden = n === 0;
    });
  }

  // ------------------------------------------------------------- filter --
  function filterOffers(offers, f) {
    let list = offers;
    if (f.q) {
      const q = f.q.trim().toLowerCase();
      if (q) list = list.filter(o => [o.store_name, o.title, o.title_ar, o.description, o.category, o.subcategory, o.mall_name, ...(o.tags || []), ...(o.products || [])]
        .filter(Boolean).some(v => String(v).toLowerCase().includes(q)));
    }
    if (f.cat) list = list.filter(o => o.category === f.cat);
    if (f.mall) list = list.filter(o => o.mall_name === f.mall);
    if (f.verifiedOnly) list = list.filter(o => !o.needs_review);
    if (f.hasPromo) list = list.filter(o => !!o.promo_code);
    const sort = f.sort || "new";
    const arr = list.slice();
    if (sort === "new") arr.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""));
    else if (sort === "expiry") arr.sort((a, b) => (a.end_date || "9999").localeCompare(b.end_date || "9999"));
    else if (sort === "az") arr.sort((a, b) => a.store_name.localeCompare(b.store_name));
    else if (sort === "disc") arr.sort((a, b) => discountNum(b.discount_text) - discountNum(a.discount_text));
    return arr;
  }

  // --------------------------------------------------------- navigation --
  function buildHeader(active) {
    const tr = t();
    const favN = Favorites.count();
    return `
    <a class="skip-link" href="#main">${tr.skip}</a>
    <header class="site-header">
      <div class="wrap bar">
        <button class="mobile-nav-toggle" id="navToggle" aria-expanded="false" aria-controls="mainNav" aria-label="${tr.menu}">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
        </button>
        <a class="brand" href="index.html">
          <svg class="mark" viewBox="0 0 34 34" aria-hidden="true"><rect width="34" height="34" rx="9" fill="var(--maroon)"/><path d="M9 11h16v3.2l-5 2.1 5 2.1V22H9v-3.2l5-2.1-5-2.1Z" fill="var(--on-maroon)"/></svg>
          <span>${tr.app}</span>
        </a>
        <nav class="main-nav" id="mainNav">
          <a href="index.html" aria-current="${active === "home" ? "page" : "false"}">${tr.nav_home}</a>
          <a href="index.html#browse" aria-current="${active === "browse" ? "page" : "false"}">${tr.nav_browse}</a>
          <a href="merchant.html" aria-current="${active === "merchants" ? "page" : "false"}">${tr.nav_merchants}</a>
          <a href="index.html#favorites" aria-current="${active === "favorites" ? "page" : "false"}">${tr.nav_favorites}</a>
          <a href="admin.html" aria-current="${active === "admin" ? "page" : "false"}">${tr.nav_admin}</a>
        </nav>
        <div class="head-actions">
          <button class="icon-btn" id="favLink" type="button" title="${tr.nav_favorites}" aria-label="${tr.nav_favorites}">
            <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7.5-4.6-10-9.2C.3 8 2 4.5 5.6 4a5 5 0 0 1 6.4 2.3A5 5 0 0 1 18.4 4C22 4.5 23.7 8 22 11.8 19.5 16.4 12 21 12 21Z"/></svg>
            <span class="badge-count" data-fav-count hidden></span>
          </button>
          <button class="icon-btn" id="themeToggle" type="button" title="${tr.theme_toggle}" aria-label="${tr.theme_toggle}">
            <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>
          </button>
          <button class="pill-btn" id="langToggle" type="button">${tr.lang_toggle}</button>
        </div>
      </div>
    </header>`;
  }

  function buildFooter() {
    const tr = t();
    const d = new Date().getFullYear();
    return `<footer class="site-footer"><div class="wrap">
      <span>© ${d} ${tr.app}. ${tr.origin_note}</span>
      <span><a href="admin.html">${tr.nav_admin}</a></span>
    </div></footer>`;
  }

  function wireChrome(active) {
    applyHtmlLangDir();
    document.getElementById("header-slot").innerHTML = buildHeader(active);
    document.getElementById("footer-slot").innerHTML = buildFooter();
    updateFavCount();
    const toggle = document.getElementById("navToggle");
    const nav = document.getElementById("mainNav");
    if (toggle) toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    document.getElementById("favLink").addEventListener("click", () => { location.href = "index.html#favorites"; });
    document.getElementById("themeToggle").addEventListener("click", () => {
      const cur = getTheme();
      const next = cur === "dark" ? "light" : cur === "light" ? "" : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
      setTheme(next);
      applyHtmlLangDir();
    });
    document.getElementById("langToggle").addEventListener("click", () => {
      setLang(getLang() === "en" ? "ar" : "en");
      location.reload();
    });
  }

  function qs(name) { return new URLSearchParams(location.search).get(name); }

  function setSEO({ title, description, canonical }) {
    if (title) document.title = title;
    const ensure = (sel, attrs) => {
      let el = document.querySelector(sel);
      if (!el) { el = document.createElement(sel.startsWith("link") ? "link" : "meta"); document.head.appendChild(el); }
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    };
    if (description) {
      ensure('meta[name="description"]', { name: "description", content: description });
      ensure('meta[property="og:description"]', { property: "og:description", content: description });
    }
    if (title) ensure('meta[property="og:title"]', { property: "og:title", content: title });
    if (canonical) ensure('link[rel="canonical"]', { rel: "canonical", href: canonical });
  }

  function injectJsonLd(obj) {
    const s = document.createElement("script");
    s.type = "application/ld+json";
    s.textContent = JSON.stringify(obj);
    document.head.appendChild(s);
  }

  global.QO = {
    TAXONOMY, CAT_ORDER, iconSvg, categoryIcon, categoryLabel,
    getLang, setLang, getTheme, setTheme, t, applyHtmlLangDir,
    Favorites, Recents, Profile,
    esc, qatarToday, daysLeft, fmtPrice, debounce, slug, unslug, discountNum,
    loadData, offerCard, offerMedia, offerTitle, expiryBadge, skeletonCards,
    emptyState, errorState, paginate, renderPagination, toast, shareOffer,
    wireFavButtons, updateFavCount, filterOffers, wireChrome, qs, setSEO, injectJsonLd,
  };
})(window);
