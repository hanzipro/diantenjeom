// localStorage-backed preference persistence + weight slider wiring.
// Everything else (vertical / serif / lang / punct) is pure CSS via
// :has() — see article.css.
const STORAGE_KEY = 'diantenjeom-prefs';

function restorePrefs() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { }
  for (const [name, value] of Object.entries(saved)) {
    for (const $el of document.querySelectorAll(`input[name="${name}"]`)) {
      if ($el.type === 'checkbox') $el.checked = (value === true);
      else if ($el.type === 'radio') $el.checked = ($el.value === value);
      else if ($el.type === 'range') $el.value = value;
    }
  }
}

function savePrefs() {
  const prefs = {};
  for (const $el of document.querySelectorAll('input[name]')) {
    if ($el.type === 'checkbox') prefs[$el.name] = $el.checked;
    else if ($el.type === 'radio' && $el.checked) prefs[$el.name] = $el.value;
    else if ($el.type === 'range') prefs[$el.name] = $el.value;
  }
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)); } catch { }
}

function applyWeight() {
  const $w = document.querySelector('input[name=weight]');
  document.querySelector('output[name=weight]').textContent = $w.value;
  for (const $a of document.querySelectorAll('article')) {
    $a.style.fontWeight = $w.value;
  }
}

// ---- Language switcher: hash-routed scrollspy. No localStorage.
// <nav class="lang-toc"> links to #zh-Hant / #ja / etc. As the user
// scrolls past an article, replaceState updates the hash and the
// active link marker. Click on a link → smooth scroll + hash update.
// Browser back/forward triggers hashchange → smooth scroll.
const articles = document.querySelectorAll('article[data-lang]');
const navLinks = document.querySelectorAll('nav.lang-toc a');
let activeLang = null;
let programmaticScrollUntil = 0;

function setActive(lang, { skipHash = false } = {}) {
  if (lang === activeLang) return;
  activeLang = lang;
  for (const a of navLinks) {
    a.setAttribute('aria-current', a.hash === '#' + lang ? 'true' : 'false');
  }
  // <html lang> follows the active article for IME / a11y hints.
  // Per-article `lang` attributes still override this for the actual
  // content; root lang is just the "page-level" default.
  document.documentElement.lang = lang;
  if (!skipHash) {
    const url = new URL(window.location.href);
    url.hash = lang;
    window.history.replaceState(null, '', url);
  }
}

// IntersectionObserver tracks which article occupies the viewport
// middle band. rootMargin clips the visible region to a 20% middle
// slice so we don't flip between adjacent articles at their borders.
const observer = new IntersectionObserver((entries) => {
  if (Date.now() < programmaticScrollUntil) return;
  let best = null;
  let bestRatio = 0;
  for (const e of entries) {
    if (e.isIntersecting && e.intersectionRatio > bestRatio) {
      best = e.target;
      bestRatio = e.intersectionRatio;
    }
  }
  if (best) setActive(best.dataset.lang);
}, {
  rootMargin: '0px -40% 0px -40%',
  threshold: [0, 0.25, 0.5, 0.75, 1],
});
for (const a of articles) observer.observe(a);

function scrollToLang(lang, behavior = 'smooth') {
  const target = document.getElementById(lang);
  if (!target) return false;
  // Suppress IntersectionObserver-driven hash updates during the
  // scroll animation, otherwise scrolling past intermediate articles
  // would clobber the user's intended target.
  programmaticScrollUntil = Date.now() + 1000;
  const scroller = document.scrollingElement || document.documentElement;
  const tRect = target.getBoundingClientRect();
  const left = scroller.scrollLeft + tRect.left
    - (scroller.clientWidth - target.offsetWidth) / 2;
  scroller.scrollTo({ left, top: scroller.scrollTop, behavior });
  setActive(lang, { skipHash: false });
  return true;
}

// Click on TOC link: prevent default jump, do smooth scroll instead.
for (const a of navLinks) {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    scrollToLang(a.hash.slice(1));
  });
}

// Back / forward buttons or manual hash edit.
window.addEventListener('hashchange', () => {
  const lang = window.location.hash.slice(1);
  if (lang) scrollToLang(lang);
});

// On load: honour initial hash if valid, otherwise mark first article
// active without modifying the URL.
const initialLang = window.location.hash.slice(1);
if (initialLang && document.getElementById(initialLang)) {
  scrollToLang(initialLang, 'auto');
} else {
  const first = articles[0].dataset.lang;
  scrollToLang(first, 'auto');
  setActive(first, { skipHash: true });
}

// Vertical-rl wants column-count to grow with content (CSS can't do
// this natively — multi-column balances or overflows but won't add
// more columns as content grows). Compute the count by:
//   1. Collapsing the article into a single column with height auto
//      so the browser lays out the full content extent.
//   2. Reading scrollHeight = total inline-axis extent needed.
//   3. Dividing by a chosen per-column inline-size (viewport height
//      minus header) to get how many columns to actually use.
// Then lock column-count + height + column-fill: auto so each column
// fills sequentially to the chosen per-column height.
function fitArticle(article) {
  const cs = getComputedStyle(article);
  const isVertical = cs.writingMode.startsWith('vertical');
  const fontSize = parseFloat(cs.fontSize);

  // Horizontal mode is pure CSS (`columns: 3 auto`, balanced,
  // block-size auto-grows). Just clear any inline styles JS set
  // while we were in vertical mode and return.
  if (!isVertical) {
    article.style.columnCount = '';
    article.style.columnWidth = '';
    article.style.columnFill = '';
    article.style.inlineSize = '';
    article.style.height = '';
    return;
  }

  const pageInline = parseFloat(cs.blockSize);
  const colWidthPx = 12 * fontSize;

  // Reset all inline styles JS may have set so the article reflows
  // to its natural CSS state (`columns: auto 12em`, `block-size: 52em`,
  // `column-fill: auto`). In that state browsers pick column-count by
  // `floor(block-size / col-width)` ≈ 4 and the article's scrollHeight
  // reports the balanced per-column inline-axis height (= total / 4).
  article.style.columnCount = '';
  article.style.columnWidth = '';
  article.style.columnFill = '';
  article.style.inlineSize = '';
  article.style.height = '';
  void article.offsetHeight;
  const naturalScroll = article.scrollHeight;

  // Reverse out total content inline-extent, then recompute cols
  // assuming each column gets a `pageInline` (= blockSize) slot.
  const currentCols = Math.max(1, Math.floor(pageInline / colWidthPx));
  const totalContent = naturalScroll * currentCols;
  const cols = Math.max(1, Math.ceil(totalContent / pageInline));

  article.style.columnCount = cols;
  article.style.columnFill = 'auto';
  article.style.inlineSize = naturalScroll + 'px';
}

const fitArticles = () => { for (const a of articles) fitArticle(a); };
const sizeObserver = new ResizeObserver(fitArticles);
sizeObserver.observe(document.documentElement);

// Toggling writing-mode doesn't resize body, so re-fit on that change too.
document.querySelector('input[name="vertical"]')
  .addEventListener('change', () => requestAnimationFrame(fitArticles));

fitArticles();

restorePrefs();
applyWeight();

document.querySelector('input[name=weight]').addEventListener('input', () => {
  applyWeight(); savePrefs();
});
document.body.addEventListener('change', savePrefs);
