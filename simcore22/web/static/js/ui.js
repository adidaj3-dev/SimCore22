// Building blocks shared by the player app and the admin portal.

import { h, ICONS, toPar, parClass, avatar, STATUS } from './dom.js';

export const icon = (name) => h('span', { class: 'ico', html: ICONS[name] });

export const parChip = (n) => h('span', { class: `par-chip ${parClass(n)}` }, toPar(n));

export function statusBadge(status) {
  const s = STATUS[status] || { label: status || 'Unknown', tone: 'muted' };
  return h('span', { class: `badge ${s.tone}` }, s.label);
}

export function card(title, sub, body, actions) {
  return h('section', { class: 'card' },
    title ? h('div', { class: 'card-h' }, h('div', {}, h('h2', {}, title), sub ? h('div', { class: 'sub' }, sub) : null), actions || null) : null,
    body);
}

export function kpi(label, value, foot) {
  return h('div', { class: 'card kpi' }, h('div', { class: 'label' }, label), h('div', { class: 'value' }, value), h('div', { class: 'foot' }, foot));
}

export function emptyState(iconName, title, text, extra) {
  return h('div', { class: 'empty-state' }, h('div', { class: 'ring', html: ICONS[iconName] }), h('h3', {}, title), h('p', {}, text), extra || null);
}

export function loading(rows = 5) {
  return h('div', { class: 'card-b' }, Array.from({ length: rows }, () => h('div', { class: 'skel', style: { height: '38px', marginBottom: '10px' } }, ' ')));
}

export function toast(text) {
  const t = h('div', { class: 'toast', role: 'status' }, text);
  document.body.append(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 2400);
}

export function person(name, sub) {
  return h('div', { class: 'person' }, avatar(name), h('div', { style: { minWidth: 0 } }, h('div', { class: 'n' }, name), sub ? h('div', { class: 's' }, sub) : null));
}

/** The light / dark switch. Remembers the choice (when the browser allows it). */
export function themeButton() {
  const btn = h('button', { class: 'btn icon ghost', 'aria-label': 'Switch light / dark theme' });
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    btn.innerHTML = theme === 'dark' ? ICONS.sun : ICONS.moon;
    btn.title = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
  };
  btn.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('sc-theme', next); } catch { /* private mode: the choice just isn't remembered */ }
    apply(next);
  });
  apply(document.documentElement.dataset.theme || 'dark');
  return btn;
}

/** A handicap index for display: "+2.1" for better than scratch, "–" when there isn't one yet. */
export function fmtIndex(value) {
  if (value == null) return '–';
  return value < 0 ? `+${Math.abs(value).toFixed(1)}` : value.toFixed(1);
}

/** A scorecard-friendly hole list from a hand-entered round (skips holes not entered yet). */
export function manualHoles(round) {
  return round.holes.filter((x) => x.strokes != null).map((x) => ({ hole: x.hole, par: x.par, score: x.strokes, counted: true }));
}

/** Pairs of label / control for forms. */
export function field(label, control, hint) {
  return h('label', { class: 'field' }, h('span', { class: 'lab' }, label), control, hint ? h('span', { class: 'hint' }, hint) : null);
}

/** A modal-free confirmation: asks inline with the browser's own dialog (accessible, and fine for rare actions). */
export const confirmAction = (message) => window.confirm(message);
