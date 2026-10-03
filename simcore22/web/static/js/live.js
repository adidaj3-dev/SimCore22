// The live leaderboard (bay TVs). Receives pushed updates, keeps one element per player and
// moves it with a CSS transform, so a player climbing the board visibly glides past the others.

import { h, clear, LOGO, toPar, parClass, avatar, timeAgo } from './dom.js';
import { get, subscribe } from './api.js';

const PAGE_SECONDS = 12;        // when there are more players than fit, show pages in turn
const MOVE_BADGE_MS = 9000;     // how long a "▲2" stays next to a rank
const MIN_ROW_REM = 3.9;
const MAX_ROW_REM = 5.6;

const app = document.getElementById('app');
const state = {
  board: null, engine: null, conn: 'connecting',
  rows: new Map(),            // player name -> { el, refs, last }
  ranks: new Map(),           // player name -> rank at the previous update
  page: 0, pageSize: 8, pages: 1, pageStarted: Date.now(),
  receivedAt: null, recent: null, recentAt: 0,
};

// -------------------------------------------------------------------- skeleton

const el = {};
function build() {
  el.clock = h('div', { class: 'clock num' });
  el.status = h('span', { class: 'pill off' }, h('i', { class: 'dot' }), h('span', {}, 'Connecting'));
  el.demo = h('span', { class: 'pill demo', hidden: true }, 'Demo data');
  el.title = h('h1', {}, 'Live Leaderboard');
  el.sub = h('p', {}, '');
  el.rows = h('div', { class: 'rows' });
  el.pager = h('div', { class: 'pager' }, h('i'));
  el.empty = h('div', { class: 'empty' });
  el.updated = h('span', {}, '');
  el.mid = h('div', { class: 'mid' }, 'Powered by ', h('b', {}, 'SimCore22'));

  el.board = h('section', { class: 'board', 'aria-label': 'Leaderboard' },
    h('div', { class: 'board-head' },
      h('span', {}, 'Pos'), h('span', {}, 'Player'), h('span', { class: 'c-thru' }, 'Thru'),
      h('span', { class: 'c-num' }, 'To par'), h('span', { class: 'c-num head-gross' }, 'Gross'),
      h('span', { class: 'c-num col-net head-net' }, 'Net')),
    el.rows, el.empty, el.pager);

  clear(app).append(
    h('header', { class: 'top' },
      h('div', { class: 'brand' }, h('span', { html: LOGO }), h('div', {}, 'SimCore22', h('span', { class: 'by' }, 'Live scoring'))),
      h('div', { class: 'title' }, el.title, el.sub),
      h('div', { class: 'top-right' }, el.demo, el.status, el.clock)),
    el.board,
    h('footer', { class: 'foot' },
      el.updated,
      el.mid,
      h('div', { class: 'legend' },
        h('span', { class: 'u' }, h('i'), h('em', {}, 'Under par')),
        h('span', { class: 'e' }, h('i'), h('em', {}, 'Even')),
        h('span', { class: 'o' }, h('i'), h('em', {}, 'Over par')))));
}

// ------------------------------------------------------------------------ rows

function createRow(name) {
  const refs = {
    badge: h('span', { class: 'rank-badge' }),
    move: h('span', { class: 'move', hidden: true }),
    name: h('div', { class: 'name' }),
    meta: h('div', { class: 'meta' }),
    thru: h('div', { class: 'thru-text' }),
    pips: h('div', { class: 'pips' }),
    final: h('span', { class: 'final-chip', hidden: true }, 'FINAL'),
    par: h('div', { class: 'c-par num' }),
    gross: h('div', { class: 'c-gross num' }),
    net: h('div', { class: 'c-net col-net num' }),
  };
  const el_ = h('div', { class: 'row enter', role: 'row' },
    h('div', { class: 'c-rank' }, refs.badge, refs.move),
    h('div', { class: 'c-who' }, avatar(name), h('div', { class: 'who-text' }, refs.name, refs.meta)),
    h('div', { class: 'c-thru' }, refs.thru, refs.pips, refs.final),
    refs.par, refs.gross, refs.net);
  return { el: el_, refs, last: null, moveTimer: null, holes: 0 };
}

function updateRow(row, p, ctx) {
  const { refs } = row;

  // rank badge
  const rank = p.rank;
  refs.badge.textContent = p.tied ? `T${rank}` : String(rank);
  refs.badge.className = `rank-badge${rank <= 3 ? ` r${rank}` : ''}${p.tied ? ' tied' : ''}`;
  row.el.classList.toggle('leader', rank === 1);

  // name / meta
  refs.name.textContent = p.name;
  const meta = [p.team, p.simcore_index != null && p.simcore_index > 0 ? `HCP ${p.simcore_index}` : null].filter(Boolean);
  refs.meta.textContent = meta.join(' · ');

  // thru + pips
  const finished = ctx.holes > 0 && p.thru >= ctx.holes && ctx.knownLength;
  if (row.holes !== ctx.holes) {
    clear(refs.pips);
    for (let i = 0; i < ctx.holes; i++) refs.pips.append(h('i', { class: 'pip' }));
    row.holes = ctx.holes;
  }
  [...refs.pips.children].forEach((pip, i) => pip.classList.toggle('on', i < p.thru));
  refs.thru.replaceChildren(finished ? 'Round complete' : h('span', {}, 'Thru ', h('b', {}, p.thru)));
  refs.final.hidden = true;  // the text above already says it; the chip is reserved for formats with a final flag

  // numbers
  refs.par.textContent = toPar(p.vs_par);
  refs.par.className = `c-par num ${parClass(p.vs_par)}`;
  refs.gross.textContent = p.gross;
  refs.net.textContent = ctx.showNet && finished ? p.net : '–';

  // what changed since last time
  const last = row.last;
  if (last && (last.gross !== p.gross || last.thru !== p.thru)) {
    row.el.classList.remove('flash');
    void row.el.offsetWidth;              // restart the animation
    row.el.classList.add('flash');
  }
  const before = ctx.ranks.get(p.name);
  if (before != null && before !== rank && !ctx.firstPaint) {
    const diff = before - rank;           // positive = moved up
    refs.move.textContent = `${diff > 0 ? '▲' : '▼'}${Math.abs(diff)}`;
    refs.move.className = `move ${diff > 0 ? 'up' : 'down'}`;
    refs.move.hidden = false;
    clearTimeout(row.moveTimer);
    row.moveTimer = setTimeout(() => { refs.move.hidden = true; }, MOVE_BADGE_MS);
  }
  row.last = { gross: p.gross, thru: p.thru };
}

function layoutRows(players) {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const avail = el.rows.clientHeight || 400;
  const minRow = MIN_ROW_REM * rem;
  const fit = Math.max(3, Math.floor(avail / minRow));            // most rows that fit at a readable size
  state.pages = Math.max(1, Math.ceil(players.length / fit));
  state.pageSize = Math.max(1, Math.ceil(players.length / state.pages)); // spread players evenly over the pages
  if (state.page >= state.pages) state.page = 0;

  const visibleCount = Math.max(1, Math.min(players.length, state.pageSize));
  const rowH = Math.min(MAX_ROW_REM * rem, avail / visibleCount);
  el.rows.style.setProperty('--row-h', `${rowH}px`);

  players.forEach((p, i) => {
    const row = state.rows.get(p.name);
    if (!row) return;
    const y = (i % state.pageSize) * rowH;
    row.el.style.transform = `translateY(${y}px)`;
    row.el.style.setProperty('--y', `${y}px`);
    row.el.classList.toggle('hidden', Math.floor(i / state.pageSize) !== state.page);
  });
  el.pager.classList.toggle('show', state.pages > 1);
}

// ----------------------------------------------------------------- applying data

function setStatus(kind, text) {
  el.status.className = `pill ${kind}`;
  el.status.lastChild.textContent = text;
}

function refreshStatus() {
  const players = state.board?.players || [];
  const isDemo = Boolean(state.board?.demo || state.engine?.demo);
  el.demo.hidden = !isDemo;
  el.mid.replaceChildren(...(isDemo ? [h('b', {}, 'Demo data'), ' \u00b7 fictional players'] : ['Powered by ', h('b', {}, 'SimCore22')]));

  if (state.conn === 'offline') return setStatus('off', 'Reconnecting');
  if (state.engine && state.engine.known && !state.engine.online && !isDemo) {
    return setStatus('off', 'Engine offline');
  }
  if (state.board?.round_complete) return setStatus('final', 'Final');
  if (players.length) return setStatus('live', 'Live');
  setStatus('wait', 'Waiting for tee-off');
  el.status.className = 'pill';
}

function applyBoard(board) {
  const firstPaint = state.board === null;
  state.board = board;
  const players = board.players || [];

  el.title.textContent = board.league_name || 'Live Leaderboard';
  const subtitle = [board.week ? `Week ${board.week}` : null, board.course_name && board.course_name !== 'Unknown' ? board.course_name : null, board.format]
    .filter(Boolean).join(' · ');
  el.sub.textContent = subtitle;
  document.title = `${board.league_name || 'Live Leaderboard'} · SimCore22`;

  const knownLength = board.holes_total != null;
  const holes = knownLength ? board.holes_total : Math.max(9, ...players.map((p) => p.thru), 0);
  const ctx = { holes, knownLength, showNet: knownLength, ranks: state.ranks, firstPaint };
  el.board.classList.toggle('no-net', !knownLength);

  const seen = new Set();
  for (const p of players) {
    let row = state.rows.get(p.name);
    if (!row) {
      row = createRow(p.name);
      state.rows.set(p.name, row);
      el.rows.append(row.el);
    }
    updateRow(row, p, ctx);
    seen.add(p.name);
  }
  for (const [name, row] of state.rows) {
    if (!seen.has(name)) { row.el.remove(); state.rows.delete(name); }
  }
  state.ranks = new Map(players.map((p) => [p.name, p.rank]));

  layoutRows(players);
  showEmpty(players.length === 0);
  state.receivedAt = Date.now();
  refreshStatus();
}

// ------------------------------------------------------------------ empty state

async function showEmpty(isEmpty) {
  el.empty.classList.toggle('show', isEmpty);
  if (!isEmpty) return;

  if (!state.recent || Date.now() - state.recentAt > 30000) {
    state.recentAt = Date.now();
    try { state.recent = (await get('/api/rounds', { limit: 6, status: 'completed' })).rounds; }
    catch { state.recent = []; }
  }
  const recent = state.recent || [];
  el.empty.replaceChildren(...[
    h('div', { class: 'ball' }),
    h('h2', {}, 'Waiting for the next round'),
    h('p', {}, 'Scores appear here the moment a player takes their first shot.'),
    recent.length ? h('div', { class: 'recent' },
      h('h3', {}, 'Recent rounds'),
      recent.map((r) => h('div', { class: 'recent-row' },
        avatar(r.player),
        h('div', { class: 'n' }, r.player),
        h('div', { class: 'c' }, [r.course !== 'Unknown' ? r.course : null, timeAgo(r.finished_at)].filter(Boolean).join(' · ')),
        h('div', { class: `s num ${parClass(r.vs_par)}` }, toPar(r.vs_par))))) : null,
  ].filter(Boolean));  // (append(null) would print the word "null")
}

// ------------------------------------------------------------------ housekeeping

function tick() {
  el.clock.textContent = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  el.updated.textContent = state.receivedAt ? `Updated ${timeAgo(new Date(state.receivedAt).toISOString())}` : '';

  // page through long boards
  if (state.pages > 1) {
    const elapsed = (Date.now() - state.pageStarted) / 1000;
    el.pager.firstChild.style.width = `${Math.min(100, (elapsed / PAGE_SECONDS) * 100)}%`;
    if (elapsed >= PAGE_SECONDS) {
      state.page = (state.page + 1) % state.pages;
      state.pageStarted = Date.now();
      layoutRows(state.board.players);
    }
  }
}

function setupKiosk() {
  let idleTimer;
  const wake = () => {
    document.body.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => document.body.classList.add('idle'), 3000);
  };
  window.addEventListener('mousemove', wake);
  wake();

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  };
  window.addEventListener('keydown', (e) => { if (e.key === 'f' || e.key === 'F') toggleFullscreen(); });
  window.addEventListener('dblclick', toggleFullscreen);
  window.addEventListener('resize', () => state.board && layoutRows(state.board.players || []));
}

// ------------------------------------------------------------------------ start

build();
setupKiosk();
tick();
setInterval(tick, 1000);
subscribe(
  ({ leaderboard, engine }) => { state.engine = engine; applyBoard(leaderboard); },
  (conn) => { state.conn = conn; refreshStatus(); },
);
