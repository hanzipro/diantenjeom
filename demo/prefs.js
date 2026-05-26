const STORAGE_KEY = 'diantenjeom-prefs';

export function restorePrefs() {
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

export function savePrefs() {
  const prefs = {};
  for (const $el of document.querySelectorAll('input[name]')) {
    if ($el.type === 'checkbox') prefs[$el.name] = $el.checked;
    else if ($el.type === 'radio' && $el.checked) prefs[$el.name] = $el.value;
    else if ($el.type === 'range') prefs[$el.name] = $el.value;
  }
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)); } catch { }
}

export function initPrefs() {
  restorePrefs();
  document.body.addEventListener('change', savePrefs);
}
