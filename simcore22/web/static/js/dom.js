// Tiny DOM helpers + formatters shared by both front ends.
// Player names, courses etc. are always inserted as TEXT (never innerHTML), so a name like
// "<script>" can't do anything. `html` is only used for the static icon strings below.

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'html') el.innerHTML = value;
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

// ------------------------------------------------------------------ formatting

const MINUS = '−';

export function toPar(n) {
  if (n == null) return '–';
  if (n === 0) return 'E';
  return n > 0 ? `+${n}` : `${MINUS}${Math.abs(n)}`;
}

export function parClass(n) {
  if (n == null) return '';
  return n < 0 ? 'under' : n > 0 ? 'over' : 'even';
}

export function fmtNumber(n, digits = 0) {
  return n == null ? '–' : Number(n).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmtDateTime(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export function fmtDay(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return '–';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? 'yesterday' : `${d} days ago`;
}

export function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/);
  return ((parts[0]?.[0] || '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

// A stable color per person, so the same player always looks the same everywhere.
export function avatarHue(name) {
  let hash = 0;
  for (const ch of String(name)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 360;
}

export function avatar(name, size = '') {
  const hue = avatarHue(name);
  return h('span', {
    class: `avatar ${size}`,
    'aria-hidden': 'true',
    style: { background: `linear-gradient(135deg, hsl(${hue} 62% 46%), hsl(${(hue + 40) % 360} 62% 36%))` },
  }, initials(name));
}

export const STATUS = {
  completed: { label: 'Completed', tone: 'ok' },
  ended_early: { label: 'Ended early', tone: 'warn' },
  abandoned: { label: 'Abandoned', tone: 'muted' },
  snapshot: { label: 'Checkpoint', tone: 'info' },
};

export function plural(n, one, many = one + 's') { return `${n} ${n === 1 ? one : many}`; }

// ----------------------------------------------------------------------- icons
// 24x24, stroke icons. Static strings only.
const icon = (paths) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;

export const ICONS = {
  overview: icon('<rect x="3" y="3" width="7.5" height="9" rx="2"/><rect x="13.5" y="3" width="7.5" height="5.5" rx="2"/><rect x="13.5" y="11.5" width="7.5" height="9.5" rx="2"/><rect x="3" y="15" width="7.5" height="6" rx="2"/>'),
  live: icon('<path d="M6 4h12v3a6 6 0 0 1-12 0V4z"/><path d="M6 6H3.5a2.5 2.5 0 0 0 2.6 3.2M18 6h2.5a2.5 2.5 0 0 1-2.6 3.2"/><path d="M12 13v4M8.5 20.5h7M9.5 17h5"/>'),
  rounds: icon('<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>'),
  players: icon('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.4c2 .8 3.5 2.6 3.5 5.6"/>'),
  system: icon('<path d="M3 12h4l2.5-7 5 14L17 12h4"/>'),
  search: icon('<circle cx="11" cy="11" r="6.5"/><path d="M20.5 20.5 16 16"/>'),
  sun: icon('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>'),
  moon: icon('<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>'),
  external: icon('<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H10"/>'),
  close: icon('<path d="M6 6l12 12M18 6 6 18"/>'),
  check: icon('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
  shield: icon('<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8-7.5 9.5-4.3-1.5-7.5-4.9-7.5-9.5V6L12 3z"/><path d="M9 12l2.2 2.2L15.5 10"/>'),
  alert: icon('<path d="M12 3.5 2.8 19.5h18.4L12 3.5z"/><path d="M12 10v4.5M12 17.4v.1"/>'),
  camera: icon('<path d="M4 8h3l1.6-2.5h6.8L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.4"/>'),
  copy: icon('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'),
  menu: icon('<path d="M4 7h16M4 12h16M4 17h16"/>'),
  arrowUp: icon('<path d="M12 19V5M6 11l6-6 6 6"/>'),
  arrowDown: icon('<path d="M12 5v14M6 13l6 6 6-6"/>'),
};

export const LOGO = `<svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3BE3A4"/><stop offset="1" stop-color="#0FA37F"/></linearGradient></defs><rect width="32" height="32" rx="9" fill="url(#lg)"/><path d="M11.5 24.5V7.8l10 4.6-10 4.6" fill="none" stroke="#032A1E" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/><circle cx="21.2" cy="23.6" r="2.3" fill="#032A1E"/></svg>`;
