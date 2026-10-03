// A golf scorecard with the traditional scoring marks:
//   birdie = circle, eagle or better = double circle, bogey = square, double bogey or worse = double square.
// A hole the player quit part-way through is dashed and not counted in the totals.

import { h, toPar, parClass } from './dom.js';

const SEGMENTS = [{ from: 1, to: 9, total: 'OUT' }, { from: 10, to: 18, total: 'IN' }];

export function markFor(hole) {
  if (!hole.counted) return 'open';
  const diff = hole.score - hole.par;
  if (diff <= -2) return 'eagle';
  if (diff === -1) return 'birdie';
  if (diff === 0) return '';
  return diff === 1 ? 'bogey' : 'double';
}

const MARK_HINT = {
  eagle: 'Eagle or better', birdie: 'Birdie', bogey: 'Bogey', double: 'Double bogey or worse',
  open: 'Unfinished hole (not counted)',
};

function segmentTable(holes, seg) {
  const cells = [];
  for (let n = seg.from; n <= seg.to; n++) cells.push(holes.get(n) || { hole: n, missing: true });
  const played = cells.filter((c) => !c.missing && c.counted);
  const parTotal = played.reduce((sum, c) => sum + (c.par ?? 4), 0);
  const scoreTotal = played.reduce((sum, c) => sum + c.score, 0);
  const anyAssumed = played.some((c) => c.par_assumed);

  return h('table', { class: 'sc' },
    h('thead', {}, h('tr', {}, h('th', { class: 'lab' }, 'Hole'), cells.map((c) => h('th', {}, c.hole)), h('th', { class: 'tot' }, seg.total))),
    h('tbody', {},
      h('tr', { class: 'par' }, h('th', { class: 'lab' }, 'Par'),
        cells.map((c) => h('td', { title: c.par_assumed ? 'Par not known yet; assumed 4' : null }, c.missing ? '' : `${c.par ?? 4}${c.par_assumed ? '*' : ''}`)),
        h('td', { class: 'tot' }, played.length ? `${parTotal}${anyAssumed ? '*' : ''}` : '')),
      h('tr', { class: 'score' }, h('th', { class: 'lab' }, 'Score'),
        cells.map((c) => {
          if (c.missing) return h('td', { class: 'gap' }, '·');
          const mark = markFor({ ...c, par: c.par ?? 4 });
          return h('td', {}, h('span', { class: `mark ${mark}`, title: MARK_HINT[mark] || null }, c.score));
        }),
        h('td', { class: 'tot' }, played.length ? scoreTotal : ''))));
}

/** holes: [{hole, par, par_assumed, score, counted}] from /api/rounds/<id>/<player> */
export function scorecard(holesList) {
  const holes = new Map(holesList.map((x) => [x.hole, x]));
  const segments = SEGMENTS.filter((seg) => holesList.some((x) => x.hole >= seg.from && x.hole <= seg.to));
  const counted = holesList.filter((x) => x.counted);
  const toParTotal = counted.reduce((sum, x) => sum + (x.score - (x.par ?? 4)), 0);

  const used = new Set(holesList.map((x) => markFor({ ...x, par: x.par ?? 4 })).filter(Boolean));
  const legend = ['eagle', 'birdie', 'bogey', 'double', 'open']
    .filter((m) => used.has(m))
    .map((m) => h('span', {}, h('span', { class: `mark ${m}` }, m === 'open' ? '' : '•'), MARK_HINT[m]));

  return {
    element: h('div', {},
      h('div', { class: 'sc-wrap' }, segments.map((seg) => segmentTable(holes, seg))),
      legend.length ? h('div', { class: 'legend-row' }, legend) : null),
    toParTotal,
    toParClass: parClass(toParTotal),
    toParText: toPar(toParTotal),
  };
}
