// Small hand-built SVG charts. No chart library: the portal has to work offline at a bay.

import { h, toPar, fmtDay } from './dom.js';

const NS = 'http://www.w3.org/2000/svg';
let uid = 0;

function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  for (const child of children.flat()) if (child != null) el.append(child.nodeType ? child : document.createTextNode(child));
  return el;
}

function niceMax(value) {
  if (value <= 4) return 4;
  if (value <= 10) return Math.ceil(value / 2) * 2;
  const step = value <= 40 ? 5 : value <= 100 ? 10 : 50;
  return Math.ceil(value / step) * step;
}

/** Vertical bars. data: [{label, value, title?}] */
export function barChart(data, { height = 190, labelEvery = 2 } = {}) {
  const W = 640, H = height, padL = 30, padR = 4, padT = 10, padB = 26;
  const id = `bg${uid++}`;
  const max = niceMax(Math.max(1, ...data.map((d) => d.value)));
  const plotH = H - padT - padB;
  const slot = (W - padL - padR) / Math.max(1, data.length);
  const barW = Math.min(34, slot * 0.58);

  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Bar chart' },
    s('defs', {}, s('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 },
      s('stop', { offset: 0, 'stop-color': 'var(--brand)' }), s('stop', { offset: 1, 'stop-color': 'var(--brand)', 'stop-opacity': 0.35 }))));

  for (const tick of [0, max / 2, max]) {
    const y = padT + plotH - (tick / max) * plotH;
    svg.append(s('line', { class: 'grid', x1: padL, x2: W - padR, y1: y, y2: y }), s('text', { x: padL - 8, y: y + 4, 'text-anchor': 'end' }, Math.round(tick)));
  }
  data.forEach((d, i) => {
    const bh = (d.value / max) * plotH;
    const x = padL + i * slot + (slot - barW) / 2;
    svg.append(s('rect', { class: 'bar-rect', x, y: padT + plotH - bh, width: barW, height: Math.max(bh, d.value ? 2 : 0), rx: 5, fill: `url(#${id})`, style: `animation-delay:${i * 25}ms` },
      s('title', {}, d.title || `${d.label}: ${d.value}`)));
    if (i % labelEvery === (data.length - 1) % labelEvery) {
      svg.append(s('text', { x: x + barW / 2, y: H - 7, 'text-anchor': 'middle' }, d.label));
    }
  });
  return svg;
}

/** Tiny trend line. values are scores to par (lower = better); drawn so UP means better. */
export function sparkline(values) {
  const W = 100, H = 30, pad = 3;
  const svg = s('svg', { class: 'spark', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Recent scores to par, improving upward' });
  if (!values || values.length < 2) {
    svg.append(s('line', { x1: 0, x2: W, y1: H / 2, y2: H / 2, stroke: 'var(--line)', 'stroke-width': 2, 'stroke-dasharray': '3 4', 'vector-effect': 'non-scaling-stroke' }));
    return svg;
  }
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * W, pad + ((v - lo) / span) * (H - 2 * pad)]); // higher score -> lower on screen
  const id = `sg${uid++}`;
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  svg.append(
    s('defs', {}, s('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 },
      s('stop', { offset: 0, 'stop-color': 'var(--brand)', 'stop-opacity': 0.28 }), s('stop', { offset: 1, 'stop-color': 'var(--brand)', 'stop-opacity': 0 }))),
    s('polygon', { points: `0,${H} ${line} ${W},${H}`, fill: `url(#${id})` }),
    s('polyline', { points: line, fill: 'none', stroke: 'var(--brand)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'vector-effect': 'non-scaling-stroke' }));
  return svg;
}

/** Score-to-par over time. points: [{label, value}] oldest first. UP means better. */
export function lineChart(points, { height = 210 } = {}) {
  const W = 640, H = height, padL = 38, padR = 12, padT = 14, padB = 28;
  const svg = s('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Score to par by round; higher on the chart is better' });
  if (points.length === 0) return svg;

  const values = points.map((p) => p.value);
  const lo = Math.min(0, ...values) - 1, hi = Math.max(0, ...values) + 1;
  const plotH = H - padT - padB, plotW = W - padL - padR;
  const y = (v) => padT + ((v - lo) / (hi - lo)) * plotH;       // bigger number = worse = lower on screen
  const x = (i) => padL + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);

  const step = Math.max(1, Math.ceil((hi - lo) / 4));
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
    if (t === 0) continue;
    svg.append(s('line', { class: 'grid', x1: padL, x2: W - padR, y1: y(t), y2: y(t) }), s('text', { x: padL - 8, y: y(t) + 4, 'text-anchor': 'end' }, toPar(t)));
  }
  svg.append(s('line', { class: 'zero', x1: padL, x2: W - padR, y1: y(0), y2: y(0) }), s('text', { x: padL - 8, y: y(0) + 4, 'text-anchor': 'end' }, 'E'));

  const id = `lg${uid++}`;
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  svg.append(
    s('defs', {}, s('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 },
      s('stop', { offset: 0, 'stop-color': 'var(--brand)', 'stop-opacity': 0 }), s('stop', { offset: 1, 'stop-color': 'var(--brand)', 'stop-opacity': 0.22 }))),
    points.length > 1 ? s('polygon', { points: `${x(0)},${padT} ${line} ${x(points.length - 1)},${padT}`, fill: `url(#${id})` }) : null,
    points.length > 1 ? s('polyline', { points: line, fill: 'none', stroke: 'var(--brand)', 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }) : null);
  points.forEach((p, i) => svg.append(s('circle', { cx: x(i), cy: y(p.value), r: 4.5, fill: 'var(--surface)', stroke: 'var(--brand)', 'stroke-width': 2.5 },
    s('title', {}, `${p.label}: ${toPar(p.value)}`))));

  const every = Math.max(1, Math.ceil(points.length / 6));
  points.forEach((p, i) => { if (i % every === 0 || i === points.length - 1) svg.append(s('text', { x: x(i), y: H - 8, 'text-anchor': 'middle' }, p.label)); });
  return svg;
}

/** Proportional bar + legend. parts: [{label, value, color}] */
export function stackedBar(parts) {
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  const pct = (v) => (total ? Math.round((v / total) * 100) : 0);
  return h('div', {},
    h('div', { class: 'stack', role: 'img', 'aria-label': parts.map((p) => `${p.label} ${pct(p.value)} percent`).join(', ') },
      parts.filter((p) => p.value > 0).map((p) => h('i', { style: { width: `${(p.value / total) * 100}%`, background: p.color }, title: `${p.label}: ${p.value}` }))),
    h('div', { class: 'stack-legend' }, parts.map((p) => h('div', {},
      h('i', { style: { background: p.color } }), p.label, h('span', { class: 'v' }, p.value.toLocaleString()), h('span', { class: 'p' }, `${pct(p.value)}%`)))));
}

export { fmtDay };
