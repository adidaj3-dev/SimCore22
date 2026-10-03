// SimCore22 admin portal: a small hash-routed single page app (no build step, no framework).
//   #/overview   #/rounds   #/rounds/<round id>/<player>   #/players   #/players/<name>   #/system

import {
  h, clear, ICONS, LOGO, toPar, parClass, avatar, fmtDateTime, fmtDay, timeAgo, plural, STATUS, fmtNumber,
} from './dom.js';
import { get, subscribe } from './api.js';
import { barChart, sparkline, lineChart, stackedBar } from './charts.js';
import { scorecard } from './scorecard.js';

const NAV = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { id: 'rounds', label: 'Rounds', icon: 'rounds' },
  { id: 'players', label: 'Players', icon: 'players' },
  { id: 'system', label: 'System', icon: 'system' },
];
const TITLES = { overview: 'Overview', rounds: 'Rounds', players: 'Players', system: 'System' };
const ROUNDS_PAGE = 25;
const ROUND_TYPE = { league: 'League', tournament: 'Tournament', practice: 'Practice', one_off: 'Casual' };

const state = {
  engine: null, board: null, demo: false, conn: 'connecting', version: '',
  page: null, roundsVersion: undefined, view: null,   // view: the current page's { refresh?, onLive? }
};
const els = {};

// =============================================================== small components

const icon = (name) => h('span', { class: 'ico', html: ICONS[name] });
const parChip = (n) => h('span', { class: `par-chip ${parClass(n)}` }, toPar(n));

function statusBadge(status) {
  const s = STATUS[status] || { label: status || 'Unknown', tone: 'muted' };
  return h('span', { class: `badge ${s.tone}` }, s.label);
}

function sourceBadge(row) {
  return row.verified
    ? h('span', { class: 'badge ok', title: "Every hole matches GSPro's own scorecard totals" }, icon('shield'), 'Verified')
    : h('span', { class: 'badge muted', title: "Counted from shots; not matched to GSPro's scorecard" }, 'Shot count');
}

function card(title, sub, body, actions) {
  return h('section', { class: 'card' },
    title ? h('div', { class: 'card-h' }, h('div', {}, h('h2', {}, title), sub ? h('div', { class: 'sub' }, sub) : null), actions || null) : null,
    body);
}

function kpi(label, value, foot) {
  return h('div', { class: 'card kpi' }, h('div', { class: 'label' }, label), h('div', { class: 'value' }, value), h('div', { class: 'foot' }, foot));
}

function emptyState(iconName, title, text, extra) {
  return h('div', { class: 'empty-state' }, h('div', { class: 'ring', html: ICONS[iconName] }), h('h3', {}, title), h('p', {}, text), extra || null);
}

function loading(rows = 5) {
  return h('div', { class: 'card-b' }, Array.from({ length: rows }, () => h('div', { class: 'skel', style: { height: '38px', marginBottom: '10px' } }, ' ')));
}

function toast(text) {
  const t = h('div', { class: 'toast', role: 'status' }, text);
  document.body.append(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 2200);
}

function person(name, sub) {
  return h('div', { class: 'person' }, avatar(name), h('div', { style: { minWidth: 0 } }, h('div', { class: 'n' }, name), sub ? h('div', { class: 's' }, sub) : null));
}

const courseOf = (r) => (r.course && r.course !== 'Unknown' ? r.course : '–');

// ===================================================================== the shell

function buildShell() {
  els.title = h('h1', {}, '');
  els.dot = h('i', { class: 'dot' });
  els.chipText = h('span', { class: 'txt' }, 'Engine');
  els.demoFlag = h('span', { class: 'badge demo-flag', hidden: true }, 'Demo data');
  els.mode = h('b', {}, '');
  els.version = h('span', {}, '');
  els.view = h('main', { class: 'content', id: 'view', tabindex: '-1' });
  els.themeBtn = h('button', { class: 'btn icon ghost', 'aria-label': 'Switch light / dark theme', onclick: toggleTheme });
  els.menuBtn = h('button', { class: 'btn icon ghost menu-btn', 'aria-label': 'Open menu', html: ICONS.menu, onclick: () => els.app.classList.toggle('nav-open') });

  els.nav = h('nav', { class: 'nav', 'aria-label': 'Main' },
    NAV.map((n) => h('a', { href: `#/${n.id}`, 'data-id': n.id, onclick: () => els.app.classList.remove('nav-open') }, icon(n.icon), n.label)),
    h('div', { class: 'sep' }),
    h('a', { href: '/live', target: '_blank', rel: 'noopener' }, icon('live'), 'Live leaderboard', h('span', { class: 'ext', html: ICONS.external })),
    h('a', { href: '/docs', target: '_blank', rel: 'noopener' }, icon('system'), 'API reference', h('span', { class: 'ext', html: ICONS.external })));

  els.drawerTitle = h('div', { class: 'grow' });
  els.drawerBody = h('div', { class: 'drawer-b' });
  els.closeBtn = h('button', { class: 'btn icon ghost', 'aria-label': 'Close', html: ICONS.close, onclick: () => closeDrawer(true) });
  els.drawer = h('aside', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Details' },
    h('div', { class: 'drawer-h' }, els.drawerTitle, els.closeBtn), els.drawerBody);
  els.drawerWrap = h('div', { class: 'drawer-wrap' }, h('div', { class: 'backdrop', onclick: () => closeDrawer(true) }), els.drawer);

  els.app = h('div', { class: 'app' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('span', { html: LOGO }), h('div', {}, 'SimCore22', h('small', {}, 'Venue admin'))),
      els.nav,
      h('div', { class: 'side-foot' }, h('div', {}, els.mode), els.version)),
    h('div', { class: 'main' },
      h('header', { class: 'top' },
        els.menuBtn, els.title, h('div', { class: 'grow' }), els.demoFlag,
        h('a', { class: 'engine-chip', href: '#/system', title: 'Engine status' }, els.dot, els.chipText), els.themeBtn),
      els.view),
    els.drawerWrap);

  clear(document.getElementById('root')).append(els.app);
  applyTheme(document.documentElement.dataset.theme || 'dark');
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(true); });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  els.themeBtn.innerHTML = theme === 'dark' ? ICONS.sun : ICONS.moon;
  els.themeBtn.title = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('sc-theme', next); } catch { /* private mode: the choice just isn't remembered */ }
  applyTheme(next);
}

function setNavCurrent(id) {
  els.nav.querySelectorAll('a[data-id]').forEach((a) => (a.dataset.id === id ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  els.title.textContent = TITLES[id] || '';
  document.title = `${TITLES[id] || 'Admin'} · SimCore22`;
}

// ===================================================================== the drawer

let drawerReturnFocus = null;

function openDrawer({ title, subtitle, avatarName }) {
  drawerReturnFocus = document.activeElement;
  els.drawerTitle.replaceChildren(
    h('div', { class: 'person', style: { gap: '14px' } },
      avatarName ? avatar(avatarName, 'lg') : null,
      h('div', { style: { minWidth: 0 } }, h('h2', {}, title), subtitle ? h('div', { class: 'sub' }, subtitle) : null)));
  els.drawerBody.replaceChildren(loading(4));
  els.drawerWrap.classList.add('open');
  requestAnimationFrame(() => els.closeBtn.focus());
}

function closeDrawer(navigate) {
  if (!els.drawerWrap.classList.contains('open')) return;
  els.drawerWrap.classList.remove('open');
  if (drawerReturnFocus?.focus) drawerReturnFocus.focus();
  if (navigate) {
    const [page] = location.hash.replace(/^#\/?/, '').split('/');
    if (location.hash.split('/').length > 2 || (page === 'players' && location.hash.split('/')[2])) location.hash = `#/${page}`;
    else if (location.hash.split('/').length > 2) location.hash = `#/${page}`;
  }
}

// ==================================================================== overview

async function renderOverview() {
  els.view.replaceChildren(h('div', { class: 'kpis' }, Array.from({ length: 4 }, () => h('div', { class: 'card kpi skel' }, h('div', { style: { height: '88px' } })))));
  const [summary, recent] = await Promise.all([get('/api/summary'), get('/api/rounds', { limit: 8 })]);
  if (state.page !== 'overview') return;

  if (summary.total_rounds === 0) {
    els.view.replaceChildren(card(null, null, emptyState('rounds', 'No rounds yet',
      'Rounds appear here automatically the moment the engine finishes one. Want to see what this looks like with data?',
      h('div', { class: 'callout info', style: { textAlign: 'left', marginTop: '8px' } }, icon('alert'), h('div', {}, 'Start the demo league with ', h('code', {}, 'python -m simcore22.web --demo'))))),
      liveCard());
    state.view = { onLive: updateLiveCard };
    return;
  }

  const d = summary.rounds_7d - summary.rounds_prev_7d;
  const delta = d === 0
    ? h('span', {}, 'Same as the week before')
    : h('span', { class: `delta ${d > 0 ? 'up' : 'down'}`, }, h('span', { html: d > 0 ? ICONS.arrowUp : ICONS.arrowDown }), `${Math.abs(d)}`, h('span', { class: 'faint', style: { fontWeight: 500 } }, ' vs the week before'));
  const avg = summary.avg_vs_par_30d;
  const mix = summary.scoring_mix;

  els.view.replaceChildren(
    h('div', { class: 'kpis' },
      kpi('Rounds this week', fmtNumber(summary.rounds_7d), delta),
      kpi('Active players', fmtNumber(summary.players_7d), `${fmtNumber(summary.total_players)} on record`),
      kpi('Average to par', h('span', { class: parClass(avg == null ? null : Math.round(avg)) }, avg == null ? '–' : toPar(avg)), 'Completed rounds, last 30 days'),
      kpi('Verified by GSPro', summary.verified_rate_30d == null ? '–' : `${Math.round(summary.verified_rate_30d * 100)}%`, "Scores matched to GSPro's own scorecard")),
    h('div', { class: 'grid-2' },
      h('div', { class: 'stack-col' },
        card('Rounds per day', 'Last 14 days', h('div', { class: 'card-b' }, barChart(summary.rounds_by_day.map((x) => ({ label: fmtDay(x.date + 'T12:00:00'), value: x.rounds, title: `${fmtDay(x.date + 'T12:00:00')}: ${plural(x.rounds, 'round')}` }))))),
        card('Recent rounds', 'Click a row for the full scorecard',
          h('div', { class: 'card-b flush table-wrap' }, roundsTable(recent.rounds, { compact: true })),
          h('a', { class: 'btn ghost', href: '#/rounds' }, 'View all'))),
      h('div', { class: 'stack-col' },
        liveCard(),
        card('Scoring mix', 'Every counted hole, last 30 days', h('div', { class: 'card-b' }, stackedBar([
          { label: 'Eagle or better', value: mix.eagle_or_better, color: 'var(--gold)' },
          { label: 'Birdie', value: mix.birdie, color: 'var(--under)' },
          { label: 'Par', value: mix.par, color: 'var(--ok)' },
          { label: 'Bogey', value: mix.bogey, color: 'var(--over)' },
          { label: 'Double or worse', value: mix.double_or_worse, color: 'var(--text-3)' },
        ]))))));
  state.view = { onLive: updateLiveCard, refresh: renderOverview };
  updateLiveCard();
}

// The "live now" card: filled from the pushed leaderboard, so it stays current without reloading.
function liveCard() {
  return card('Live now', 'Tonight’s leaders', h('div', { id: 'live-card-body', class: 'live-list' }),
    h('a', { class: 'btn ghost', href: '/live', target: '_blank', rel: 'noopener' }, 'Open board', icon('external')));
}

function updateLiveCard() {
  const body = document.getElementById('live-card-body');
  if (!body) return;
  const players = state.board?.players || [];
  if (!players.length) {
    body.replaceChildren(h('div', { style: { padding: '8px 20px 22px' } },
      emptyState('live', 'No round in progress', 'When someone tees off, the leaders show up here live.')));
    return;
  }
  const done = state.board.holes_total;
  body.replaceChildren(...players.slice(0, 6).map((p) => h('div', { class: 'live-item' },
    h('div', { class: `rk ${p.rank === 1 ? 'first' : ''}` }, p.tied ? `T${p.rank}` : p.rank),
    person(p.name, [p.team, p.thru >= (done || 99) ? 'Finished' : `Thru ${p.thru}`].filter(Boolean).join(' · ')),
    parChip(p.vs_par))),
  h('div', { class: 'live-item', style: { gridTemplateColumns: '1fr' } }, h('span', { class: 'faint', style: { fontSize: '12.5px' } },
    `${plural(players.length, 'player')} on the board${state.board.course_name && state.board.course_name !== 'Unknown' ? ` · ${state.board.course_name}` : ''}`)));
}

// ======================================================================= rounds

function roundsTable(rows, { compact = false } = {}) {
  if (!rows.length) return emptyState('rounds', 'No rounds match', 'Try a different filter.');
  if (compact) return compactRoundsTable(rows);
  return h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', {}, 'When'), h('th', { class: 'hide-sm' }, 'Course'),
      h('th', { class: 'num' }, 'Holes'), h('th', { class: 'num' }, 'Gross'), h('th', { class: 'num' }, 'To par'),
      h('th', {}, 'Status'), h('th', { class: 'hide-sm' }, 'Scores'))),
    h('tbody', {}, rows.map((r) => {
      const open = () => { location.hash = `#/rounds/${encodeURIComponent(r.round_id)}/${encodeURIComponent(r.player)}`; };
      return h('tr', { class: 'click', tabindex: 0, role: 'link', 'aria-label': `${r.player}, ${r.course}`, onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); } },
        h('td', {}, person(r.player)),
        h('td', { class: 'muted' }, fmtDateTime(r.finished_at)),
        h('td', { class: 'muted hide-sm' }, courseOf(r)),
        h('td', { class: 'num' }, r.holes_played),
        h('td', { class: 'num' }, r.gross ?? '–'),
        h('td', { class: 'num' }, parChip(r.vs_par)),
        h('td', {}, statusBadge(r.round_status)),
        h('td', { class: 'hide-sm' }, sourceBadge(r)));
    })));
}

// The overview's narrower list: course sits under the player instead of in its own column.
function compactRoundsTable(rows) {
  return h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', {}, 'When'), h('th', { class: 'num' }, 'To par'), h('th', {}, 'Status'))),
    h('tbody', {}, rows.map((r) => {
      const open = () => { location.hash = `#/rounds/${encodeURIComponent(r.round_id)}/${encodeURIComponent(r.player)}`; };
      return h('tr', { class: 'click', tabindex: 0, role: 'link', 'aria-label': `${r.player}, ${r.course}`, onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); } },
        h('td', {}, person(r.player, courseOf(r) === '\u2013' ? null : courseOf(r))),
        h('td', { class: 'muted nowrap' }, fmtDateTime(r.finished_at)),
        h('td', { class: 'num' }, parChip(r.vs_par)),
        h('td', {}, statusBadge(r.round_status)));
    })));
}

async function renderRounds() {
  const f = { status: '', q: '', rows: [], total: 0 };
  const tableHost = h('div', { class: 'card-b flush table-wrap' });
  const countEl = h('span', { class: 'faint', style: { fontSize: '13px' } });
  const moreBtn = h('button', { class: 'btn', hidden: true, onclick: () => load(true) }, 'Load more');
  const chips = [['', 'All'], ['completed', 'Completed'], ['ended_early', 'Ended early'], ['abandoned', 'Abandoned']].map(([value, label]) =>
    h('button', { class: 'chip', 'aria-pressed': value === '' ? 'true' : 'false', onclick: (e) => {
      f.status = value; chips.forEach((c) => c.setAttribute('aria-pressed', c === e.currentTarget ? 'true' : 'false')); load(false);
    } }, label));
  let timer;
  const search = h('input', { type: 'search', placeholder: 'Search player or course', 'aria-label': 'Search rounds', oninput: (e) => {
    clearTimeout(timer); timer = setTimeout(() => { f.q = e.target.value; load(false); }, 220);
  } });

  async function load(append) {
    if (!append) tableHost.replaceChildren(loading(6));
    const res = await get('/api/rounds', { status: f.status, q: f.q, limit: ROUNDS_PAGE, offset: append ? f.rows.length : 0 });
    if (state.page !== 'rounds') return;
    f.rows = append ? f.rows.concat(res.rounds) : res.rounds;
    f.total = res.total;
    tableHost.replaceChildren(roundsTable(f.rows));
    countEl.textContent = `${fmtNumber(f.total)} ${f.total === 1 ? 'round' : 'rounds'}`;
    moreBtn.hidden = f.rows.length >= f.total;
  }

  els.view.replaceChildren(h('section', { class: 'card' },
    h('div', { class: 'toolbar' }, h('div', { class: 'chips' }, chips), h('div', { class: 'grow' }), countEl,
      h('label', { class: 'search' }, h('span', { html: ICONS.search }), search)),
    tableHost,
    h('div', { style: { padding: '14px 20px 18px', display: 'flex', justifyContent: 'center' } }, moreBtn)));
  state.view = { refresh: () => load(false) };
  await load(false);
}

async function showRound(roundId, player) {
  openDrawer({ title: player, subtitle: 'Loading round…', avatarName: player });
  let d;
  try { d = await get(`/api/rounds/${encodeURIComponent(roundId)}/${encodeURIComponent(player)}`); }
  catch { els.drawerBody.replaceChildren(emptyState('alert', 'Round not found', 'It may have been replaced by a newer record. Go back to the list and open it again.')); return; }

  const sc = scorecard(d.holes);
  const counted = d.holes.filter((x) => x.counted);
  const toParTotal = d.vs_par ?? sc.toParTotal;
  const tally = (test) => counted.filter((x) => !x.par_assumed && test(x.score - x.par)).length;
  const hasPar = counted.some((x) => !x.par_assumed);

  openDrawer({ title: d.player, subtitle: `${courseOf(d)} · ${fmtDateTime(d.finished_at)}`, avatarName: d.player });

  const callouts = [];
  if (d.round_status === 'snapshot') callouts.push(h('div', { class: 'callout info' }, icon('alert'), h('div', {}, h('b', {}, 'Checkpoint. '), 'This round was saved part-way and has not finished yet.')));
  if (d.verified) callouts.push(h('div', { class: 'callout ok' }, icon('shield'), h('div', {}, h('b', {}, 'Verified. '), "These scores were read from GSPro's scorecard and every hole adds up to its printed totals.")));
  else callouts.push(h('div', { class: 'callout warn' }, icon('alert'), h('div', {}, h('b', {}, 'Counted from shots. '), "These scores weren't matched to GSPro's scorecard, so a missed or doubled shot could throw them off. Treat as provisional.")));
  if (d.round_status === 'ended_early') callouts.push(h('div', { class: 'callout' }, icon('alert'), h('div', {}, h('b', {}, 'Ended early. '), `${plural(d.holes_played, 'hole')} counted; a hole left unfinished is shown dashed and isn't included.`)));
  if (d.round_status === 'abandoned') callouts.push(h('div', { class: 'callout' }, icon('alert'), h('div', {}, h('b', {}, 'Abandoned. '), 'The player stopped and nothing happened for a while, so the round was saved as it stood.')));

  const mini = (label, value) => h('div', {}, h('div', { class: 'label' }, label), h('div', { class: 'value' }, value));
  const body = [
    h('div', { class: 'stat-band' },
      h('div', {}, h('div', { class: 'label' }, 'To par'), h('div', { class: `value ${parClass(toParTotal)}` }, toPar(toParTotal))),
      h('div', {}, h('div', { class: 'label' }, 'Gross'), h('div', { class: 'value' }, d.gross ?? '–')),
      h('div', {}, h('div', { class: 'label' }, 'Holes'), h('div', { class: 'value' }, d.holes_played)),
      h('div', {}, h('div', { class: 'label' }, 'Handicap'), h('div', { class: 'value' }, d.handicap ?? '–'))),
    h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, statusBadge(d.round_status), sourceBadge(d),
      d.round_type ? h('span', { class: 'badge muted', title: 'How the round was classified against the league schedule' }, ROUND_TYPE[d.round_type] || d.round_type) : null),
    ...callouts,
    h('div', {}, h('div', { class: 'section-title' }, 'Scorecard'), sc.element),
    hasPar ? h('div', {}, h('div', { class: 'section-title' }, 'Scoring'), h('div', { class: 'mini-stats' },
      mini('Birdies+', tally((x) => x <= -1)), mini('Pars', tally((x) => x === 0)), mini('Bogeys', tally((x) => x === 1)), mini('Doubles+', tally((x) => x >= 2)))) : null,
    d.shots.count > 0 ? h('div', {}, h('div', { class: 'section-title' }, `Shots tracked${d.shots.devices.length ? ` · ${d.shots.devices.join(', ')}` : ''}`), h('div', { class: 'mini-stats' },
      mini('Shots', d.shots.count), mini('Avg ball speed', d.shots.avg_ball_speed != null ? `${d.shots.avg_ball_speed} mph` : '–'),
      mini('Max ball speed', d.shots.max_ball_speed != null ? `${d.shots.max_ball_speed} mph` : '–'), mini('Avg carry', d.shots.avg_carry != null ? `${d.shots.avg_carry} yd` : '–'))) : null,
    d.image ? h('div', {}, h('div', { class: 'section-title' }, "GSPro scorecard screenshot"),
      h('a', { href: `/api/scorecards/${encodeURIComponent(d.image)}`, target: '_blank', rel: 'noopener' },
        h('img', { class: 'shot-img', src: `/api/scorecards/${encodeURIComponent(d.image)}`, alt: "Screenshot of GSPro's end-of-round scorecard", loading: 'lazy' })),
      h('p', { class: 'faint', style: { marginTop: '8px', fontSize: '12.5px' } }, 'What the scores above were read from.')) : null,
    h('dl', { class: 'kv' },
      h('dt', {}, 'Ended by'), h('dd', {}, String(d.finalize_reason || '–').replace(/_/g, ' ')),
      h('dt', {}, 'Handicap used'), h('dd', {}, d.handicap_was_default ? `${d.handicap} (default – no history yet)` : d.handicap ?? '–'),
      h('dt', {}, 'Round ID'), h('dd', {}, h('code', {}, d.round_id.slice(0, 12)))),
  ].filter(Boolean);
  els.drawerBody.replaceChildren(...body);
}

// ====================================================================== players

async function renderPlayers() {
  const res = await get('/api/players');
  if (state.page !== 'players') return;
  const all = res.players;
  const gridHost = h('div', {});
  const countEl = h('span', { class: 'faint', style: { fontSize: '13px' } });

  const draw = (q = '') => {
    const rows = all.filter((p) => p.player.toLowerCase().includes(q.toLowerCase()));
    countEl.textContent = `${plural(rows.length, 'player')}`;
    gridHost.replaceChildren(rows.length ? h('div', { class: 'player-grid' }, rows.map((p) => h('button', {
      class: 'player-card', onclick: () => { location.hash = `#/players/${encodeURIComponent(p.player)}`; },
      'aria-label': `${p.player}, ${plural(p.rounds, 'round')}`,
    },
    h('div', { class: 'head' }, avatar(p.player), h('div', { class: 'nm' }, p.player),
      p.handicap != null ? h('span', { class: 'badge hc' }, `HCP ${p.handicap}`) : null),
    h('div', { class: 'nums' },
      h('div', {}, h('div', { class: 'label' }, 'Rounds'), h('div', { class: 'value' }, p.rounds)),
      h('div', {}, h('div', { class: 'label' }, 'Avg to par'), h('div', { class: `value ${parClass(p.avg_vs_par == null ? null : Math.round(p.avg_vs_par))}` }, p.avg_vs_par == null ? '–' : toPar(p.avg_vs_par))),
      h('div', {}, h('div', { class: 'label' }, 'Best'), h('div', { class: `value ${parClass(p.best_vs_par)}` }, toPar(p.best_vs_par)))),
    sparkline(p.trend),
    h('div', { class: 'when' }, `Last played ${timeAgo(p.last_played)}${p.last_course && p.last_course !== 'Unknown' ? ` · ${p.last_course}` : ''}`)))) :
      emptyState('players', all.length ? 'No players match' : 'No players yet', all.length ? 'Try a different name.' : 'Players appear here after their first finished round.'));
  };

  els.view.replaceChildren(h('section', { class: 'card' },
    h('div', { class: 'toolbar' }, h('div', { class: 'grow' }, countEl),
      h('label', { class: 'search' }, h('span', { html: ICONS.search }), h('input', { type: 'search', placeholder: 'Search players', 'aria-label': 'Search players', oninput: (e) => draw(e.target.value) }))),
    gridHost));
  state.playersCache = all;
  state.view = {};
  draw();
}

async function showPlayer(name) {
  openDrawer({ title: name, subtitle: 'Loading…', avatarName: name });
  const [{ players }, { rounds }] = await Promise.all([get('/api/players'), get('/api/rounds', { player: name, limit: 200 })]);
  const p = players.find((x) => x.player.toLowerCase() === name.toLowerCase());
  if (!p) { els.drawerBody.replaceChildren(emptyState('players', 'Player not found', 'They may not have a finished round yet.')); return; }

  openDrawer({ title: p.player, subtitle: `${plural(p.rounds, 'round')}${p.handicap != null ? ` · Handicap ${p.handicap}` : ''}`, avatarName: p.player });
  const chronological = rounds.filter((r) => r.vs_par != null && r.round_status !== 'snapshot').reverse();
  const mini = (label, value, cls = '') => h('div', {}, h('div', { class: 'label' }, label), h('div', { class: `value ${cls}` }, value));
  els.drawerBody.replaceChildren(
    h('div', { class: 'mini-stats' },
      mini('Rounds', p.rounds), mini('Avg to par', p.avg_vs_par == null ? '–' : toPar(p.avg_vs_par), parClass(p.avg_vs_par == null ? null : Math.round(p.avg_vs_par))),
      mini('Best round', toPar(p.best_vs_par), parClass(p.best_vs_par)), mini('Verified', `${Math.round(p.verified_rate * 100)}%`)),
    h('div', {}, h('div', { class: 'section-title' }, 'Score to par · up is better'),
      h('div', { class: 'card' }, h('div', { class: 'card-b' }, lineChart(chronological.map((r) => ({ label: fmtDay(r.finished_at), value: r.vs_par })))))),
    h('div', {}, h('div', { class: 'section-title' }, 'Rounds'),
      h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', {}, 'Course'), h('th', { class: 'num' }, 'To par'), h('th', {}, 'Status'))),
        h('tbody', {}, rounds.filter((r) => r.round_status !== 'snapshot').slice(0, 30).map((r) => h('tr', {
          class: 'click', tabindex: 0, onclick: () => { location.hash = `#/rounds/${encodeURIComponent(r.round_id)}/${encodeURIComponent(r.player)}`; },
        }, h('td', { class: 'muted' }, fmtDateTime(r.finished_at)), h('td', { class: 'muted' }, courseOf(r)),
        h('td', { class: 'num' }, parChip(r.vs_par)), h('td', {}, statusBadge(r.round_status))))))))));
}

// ======================================================================= system

const CAPTURE_HELP = {
  capturing: { tone: 'ok', icon: 'check', title: 'Reading the GSPro window', text: 'Screen capture is working normally.' },
  starting: { tone: 'info', icon: 'camera', title: 'Starting up', text: 'The engine is looking for the GSPro window.' },
  waiting_for_window: { tone: 'warn', icon: 'alert', title: "Can't see GSPro", text: 'Open GSPro and make sure its window isn’t minimized. Check the window title in the engine settings if it is open.' },
  black_frames: { tone: 'danger', icon: 'alert', title: 'GSPro is capturing as black', text: 'GSPro is probably in exclusive fullscreen. Switch it to Windowed or Borderless windowed in its display settings.' },
  error: { tone: 'danger', icon: 'alert', title: 'Capture hit an error', text: 'Check the engine window or the log file in the logs folder for details.' },
  disabled: { tone: '', icon: 'camera', title: 'Screen reading is off', text: 'The engine was started without screen capture.' },
};

function systemBody() {
  const e = state.engine || { known: false, online: false };
  const cap = e.capture || {};
  const help = CAPTURE_HELP[cap.state] || { tone: '', icon: 'alert', title: cap.state || 'Unknown', text: '' };
  const url = `${location.origin}/live`;

  const engineStatus = !e.known
    ? h('div', { class: 'callout warn' }, icon('alert'), h('div', {}, h('b', {}, 'Engine hasn’t reported in. '), 'Start it with ', h('code', {}, 'run_bay.bat'), ' on the bay PC. Rounds already recorded are still shown here.'))
    : e.online
      ? h('div', { class: 'callout ok' }, icon('check'), h('div', {}, h('b', {}, e.demo ? 'Demo engine. ' : 'Engine running. '), `Last heartbeat ${e.age_seconds ?? 0}s ago.`))
      : h('div', { class: 'callout danger' }, icon('alert'), h('div', {}, h('b', {}, 'Engine offline. '), `Last heard from ${timeAgo(e.updated_at)}. Start it with `, h('code', {}, 'run_bay.bat'), '.'));

  const round = e.round || {};
  return h('div', { class: 'grid-2' },
    h('div', { class: 'stack-col' },
      card('Engine', 'Scoring and screen-reading service', h('div', { class: 'card-b', style: { display: 'grid', gap: '16px' } },
        engineStatus,
        e.known ? h('dl', { class: 'kv' },
          h('dt', {}, 'Started'), h('dd', {}, e.started_at ? `${timeAgo(e.started_at)} (${fmtDateTime(e.started_at)})` : '–'),
          h('dt', {}, 'Version'), h('dd', {}, e.version || '–'),
          h('dt', {}, 'Process'), h('dd', {}, e.demo ? 'Demo' : e.pid ?? '–')) : null)),
      card('Screen capture', cap.mode ? `${cap.mode === 'window' ? 'Window' : 'Monitor'}: ${cap.target}` : null, h('div', { class: 'card-b', style: { display: 'grid', gap: '14px' } },
        e.known ? h('div', { class: `callout ${help.tone}` }, icon(help.icon), h('div', {}, h('b', {}, `${help.title}. `), help.text)) : h('p', { class: 'muted' }, 'Capture status appears once the engine is running.'),
        cap.last_frame_at ? h('dl', { class: 'kv' }, h('dt', {}, 'Last frame'), h('dd', {}, timeAgo(cap.last_frame_at))) : null)),
      card('Current round', null, h('div', { class: 'card-b' }, round.in_progress
        ? h('div', { style: { display: 'grid', gap: '12px' } }, ...round.players.map((p) => h('div', { class: 'person' }, avatar(p.name), h('div', { style: { flex: 1, minWidth: 0 } },
          h('div', { class: 'n' }, p.name), h('div', { class: 'bar', style: { marginTop: '6px' } }, h('i', { style: { width: `${Math.min(100, (p.holes / 9) * 100)}%` } }))),
        h('span', { class: 'badge' }, `${plural(p.holes, 'hole')} played`))),
        h('p', { class: 'faint', style: { fontSize: '12.5px' } }, `${plural(round.shots, 'shot')} tracked · idle ${Math.round((round.idle_seconds || 0) / 60)} min of ${round.idle_timeout_minutes} before an abandoned round is saved`))
        : h('p', { class: 'muted' }, 'No round in progress.')))),
    h('div', { class: 'stack-col' },
      card('Live leaderboard link', 'Put this on any bay screen', h('div', { class: 'card-b', style: { display: 'grid', gap: '12px' } },
        h('div', { class: 'callout' }, h('code', { style: { wordBreak: 'break-all' } }, url)),
        h('div', { style: { display: 'flex', gap: '8px' } },
          h('a', { class: 'btn primary', href: '/live', target: '_blank', rel: 'noopener' }, icon('live'), 'Open'),
          h('button', { class: 'btn', onclick: async () => { try { await navigator.clipboard.writeText(url); toast('Link copied'); } catch { toast('Copy failed – select the link instead'); } } }, icon('copy'), 'Copy link')),
        h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'For screens on other PCs, start the web UI with ', h('code', {}, '--host 0.0.0.0'), ' and use this PC’s network address. There is no login yet – use a trusted venue network.'))),
      card('Launch-monitor feed', null, h('div', { class: 'card-b' }, e.feed?.configured
        ? h('p', {}, `Connected to ${e.feed.host}:${e.feed.port}.`)
        : h('p', { class: 'muted' }, 'Not connected. Rounds are tracked from the GSPro screen; shot data (ball speed, carry) needs the launch-monitor feed.'))),
      card('About', null, h('div', { class: 'card-b' }, h('dl', { class: 'kv' },
        h('dt', {}, 'Version'), h('dd', {}, state.version || '–'),
        h('dt', {}, 'Data'), h('dd', {}, state.demo ? 'Demo league (fictional)' : 'Your venue'),
        h('dt', {}, 'API'), h('dd', {}, h('a', { href: '/docs', target: '_blank', rel: 'noopener' }, '/docs')))))));
}

function renderSystem() {
  const host = h('div', {});
  const draw = () => host.replaceChildren(systemBody());
  els.view.replaceChildren(host);
  state.view = { onLive: draw };
  draw();
}

// ====================================================================== routing

const PAGES = { overview: renderOverview, rounds: renderRounds, players: renderPlayers, system: renderSystem };

async function route() {
  const [page = 'overview', a] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const id = PAGES[page] ? page : 'overview';
  const parts = location.hash.replace(/^#\/?/, '').split('/');

  if (state.page !== id) {
    state.page = id;
    state.view = null;
    setNavCurrent(id);
    els.view.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    try { await PAGES[id](); } catch (err) { if (state.page === id) els.view.replaceChildren(card(null, null, emptyState('alert', 'Something went wrong', `${err.message}. Is the server still running?`))); }
  }

  if (id === 'rounds' && a && parts[2]) showRound(a, decodeURIComponent(parts.slice(2).join('/')));
  else if (id === 'players' && a) showPlayer(a);
  else closeDrawer(false);
}

// ======================================================================= status

function updateChrome() {
  const e = state.engine;
  els.demoFlag.hidden = !state.demo;
  els.mode.textContent = state.demo ? 'Demo data' : 'Live data';
  els.version.textContent = state.version ? `Version ${state.version}` : '';

  let dot = '', text = 'Engine';
  if (state.demo) { dot = 'demo'; text = 'Demo'; }
  else if (state.conn === 'offline') { dot = 'danger'; text = 'Server unreachable'; }
  else if (!e || !e.known) { dot = ''; text = 'Engine not started'; }
  else if (e.online) { dot = 'ok'; text = e.round?.in_progress ? `Engine online · ${plural(e.round.players.length, 'player')} on course` : 'Engine online'; }
  else { dot = 'danger'; text = 'Engine offline'; }
  els.dot.className = `dot ${dot}`;
  els.chipText.textContent = text;
}

function onLive({ leaderboard, engine, rounds_signature: signature }) {
  state.board = leaderboard;
  state.engine = engine;
  state.demo = Boolean(leaderboard?.demo || engine?.demo);
  updateChrome();
  state.view?.onLive?.();

  // a real log has 3 file stamps; refetch lists only when the round log itself changed
  const version = Array.isArray(signature) && signature.length >= 3 ? signature[2] : undefined;
  if (version !== undefined && state.roundsVersion !== undefined && version !== state.roundsVersion) state.view?.refresh?.();
  state.roundsVersion = version;
}

// ========================================================================= start

buildShell();
updateChrome();
get('/api/health').then((hlth) => { state.version = hlth.version; state.demo ||= hlth.mode === 'demo'; updateChrome(); }).catch(() => {});
subscribe(onLive, (conn) => { state.conn = conn; updateChrome(); });
window.addEventListener('hashchange', route);
setInterval(() => { if (!document.hidden) state.view?.refresh?.(); }, 60000);   // keep relative times ("5 min ago") honest
route();
