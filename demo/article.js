// localStorage-backed preference persistence + weight slider wiring.
// Everything else (vertical / serif / lang / punct) is pure CSS via
// :has() — see main.css.
import { initPrefs, savePrefs } from './prefs.js';

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
const navLinks = document.querySelectorAll('nav.lang-toc a[href^="#"]');
let activeLang = null;
let programmaticScrollUntil = 0;

function setActive(lang, { skipHash = false } = {}) {
  if (lang === activeLang) return;
  activeLang = lang;
  for (const a of navLinks) {
    a.setAttribute('aria-current', a.hash === '#' + lang ? 'true' : 'false');
  }
  document.documentElement.lang = lang;
  if (!skipHash) {
    const url = new URL(window.location.href);
    url.hash = lang;
    window.history.replaceState(null, '', url);
  }
}

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
  programmaticScrollUntil = Date.now() + 1000;
  const scroller = document.scrollingElement || document.documentElement;
  const tRect = target.getBoundingClientRect();
  const left = scroller.scrollLeft + tRect.left
    - (scroller.clientWidth - target.offsetWidth) / 2;
  scroller.scrollTo({ left, top: scroller.scrollTop, behavior });
  setActive(lang, { skipHash: false });
  return true;
}

for (const a of navLinks) {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    scrollToLang(a.hash.slice(1));
  });
}

window.addEventListener('hashchange', () => {
  const lang = window.location.hash.slice(1);
  if (lang) scrollToLang(lang);
});

const initialLang = window.location.hash.slice(1);
if (initialLang && document.getElementById(initialLang)) {
  scrollToLang(initialLang, 'auto');
} else {
  const first = articles[0].dataset.lang;
  scrollToLang(first, 'auto');
  setActive(first, { skipHash: true });
}

function fitArticle(article) {
  const cs = getComputedStyle(article);
  const isVertical = cs.writingMode.startsWith('vertical');
  const fontSize = parseFloat(cs.fontSize);

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

  article.style.columnCount = '';
  article.style.columnWidth = '';
  article.style.columnFill = '';
  article.style.inlineSize = '';
  article.style.height = '';
  void article.offsetHeight;
  const naturalScroll = article.scrollHeight;

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

document.querySelector('input[name="vertical"]')
  .addEventListener('change', () => requestAnimationFrame(fitArticles));

fitArticles();

initPrefs();
applyWeight();

document.querySelector('input[name=weight]').addEventListener('input', () => {
  applyWeight(); savePrefs();
});
