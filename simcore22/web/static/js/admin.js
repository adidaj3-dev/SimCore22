// SimCore22 venue admin: a small hash-routed single page app (no build step, no framework).
//   #/overview   #/leagues   #/leagues/<id>   #/players   #/players/<id>   #/capture   #/capture/<round>
//   #/captured   #/captured/<round id>/<player>   #/round/<hand-entered round id>   #/system

import {
  h, clear, ICONS, LOGO, toPar, parClass, avatar, fmtDateTime, fmtDay, timeAgo, plural, fmtNumber,
} from './dom.js';
import { get, subscribe, session, goToLogin, logout } from './api.js';
import { barChart, stackedBar } from './charts.js';
import { scorecard } from './scorecard.js';
import { makePages } from './admin_league.js';
import {
  icon, parChip, statusBadge, card, kpi, emptyState, loading, toast, person, themeButton,
} from './ui.js';

const NAV = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { id: 'leagues', label: 'Leagues', icon: 'leagues' },
  { id: 'players', label: 'Players', icon: 'players' },
  { id: 'capture', label: 'Capture accuracy', icon: 'target' },
  { id: 'captured', label: 'Captured rounds', icon: 'rounds' },
  { id: 'system', label: 'System', icon: 'system' },
];
const TITLES = Object.fromEntries(NAV.map((n) => [n.id, n.label]));
const ROUNDS_PAGE = 25;
const ROUND_TYPE = { league: 'League', tournament: 'Tournament', practice: 'Practice', one_off: 'Casual' };

const state = {
  engine: null, demo: false, conn: 'connecting', version: '', me: null,
  page: null, pageKey: null, baseHash: '#/overview', roundsVersion: undefined, view: null,   // view: the current page's { refresh?, onLive?, cleanup? }
};
const els = {};

// =============================================================== small components

function sourceBadge(row) {
  return row.verified
    ? h('span', { class: 'badge ok', title: "Every hole matches GSPro's own scorecard totals" }, icon('shield'), 'Verified')
    : h('span', { class: 'badge muted', title: "Counted from shots; not matched to GSPro's scorecard" }, 'Shot count');
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
  els.menuBtn = h('button', { class: 'btn icon ghost menu-btn', 'aria-label': 'Open menu', html: ICONS.menu, onclick: () => els.app.classList.toggle('nav-open') });

  els.nav = h('nav', { class: 'nav', 'aria-label': 'Main' },
    NAV.map((n) => h('a', { href: `#/${n.id}`, 'data-id': n.id, onclick: () => els.app.classList.remove('nav-open') }, icon(n.icon), n.label)),
    h('div', { class: 'sep' }),
    h('a', { href: '/live', target: '_blank', rel: 'noopener' }, icon('live'), 'Live leaderboard', h('span', { class: 'ext', html: ICONS.external })),
    h('a', { href: '/app' }, icon('flag'), 'Player app', h('span', { class: 'ext', html: ICONS.external })),
    h('a', { href: '/docs', target: '_blank', rel: 'noopener' }, icon('system'), 'API reference', h('span', { class: 'ext', html: ICONS.external })));

  els.drawerTitle = h('div', { class: 'grow' });
  els.drawerBody = h('div', { class: 'drawer-b' });
  els.closeBtn = h('button', { class: 'btn icon ghost', 'aria-label': 'Close', html: ICONS.close, onclick: () => closeDrawer(true) });
  els.drawer = h('aside', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Details' },
    h('div', { class: 'drawer-h' }, els.drawerTitle, els.closeBtn), els.drawerBody);
  els.drawerWrap = h('div', { class: 'drawer-wrap' }, h('div', { class: 'backdrop', onclick: () => closeDrawer(true) }), els.drawer);

  els.userName = h('div', { class: 'n' }, '');
  els.app = h('div', { class: 'app' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('span', { html: LOGO }), h('div', {}, 'SimCore22', h('small', {}, 'Venue admin'))),
      els.nav,
      h('div', { class: 'side-foot' },
        h('div', { class: 'side-user' }, els.userName),
        h('div', {}, els.mode), els.version,
        h('button', { class: 'btn ghost', onclick: logout }, icon('logout'), 'Log out'))),
    h('div', { class: 'main' },
      h('header', { class: 'top' },
        els.menuBtn, els.title, h('div', { class: 'grow' }), els.demoFlag,
        h('a', { class: 'engine-chip', href: '#/system', title: 'Engine status' }, els.dot, els.chipText), themeButton()),
      els.view),
    els.drawerWrap);

  clear(document.getElementById('root')).append(els.app);
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(true); });
}

function setNavCurrent(id) {
  els.nav.querySelectorAll('a[data-id]').forEach((a) => (a.dataset.id === id ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  els.title.textContent = TITLES[id] || '';
  document.title = `${TITLES[id] || 'Admin'} · SimCore22`;
}

// ===================================================================== the drawer

let drawerReturnFocus = null;

function openDrawer({ title, subtitle, avatarName }) {
  if (!els.drawerWrap.classList.contains('open')) drawerReturnFocus = document.activeElement;
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
  if (navigate && isDrawerRoute()) location.hash = state.baseHash;   // back to the page behind the drawer
}

function isDrawerRoute() {
  const [page, a] = location.hash.replace(/^#\/?/, '').split('/');
  return page === 'round' || (['players', 'capture', 'captured'].includes(page) && Boolean(a));
}

// ==================================================================== overview

async function renderOverview() {
  els.view.replaceChildren(h('div', { class: 'kpis' }, Array.from({ length: 4 }, () => h('div', { class: 'card kpi skel' }, h('div', { style: { height: '88px' } })))));
  const [ov, { leagues }] = await Promise.all([get('/api/admin/overview'), get('/api/leagues')]);
  if (state.page !== 'overview') return;
  const active = leagues.filter((l) => !l.archived);

  if (!active.length && !ov.players) {
    els.view.replaceChildren(card(null, null, emptyState('flag', 'Let’s set up your venue',
      'Create a league, give players its join code, and they can enter their rounds hole by hole. Standings, handicaps and the bay screens fill in on their own.',
      h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' } },
        h('a', { class: 'btn primary', href: '#/leagues' }, icon('plus'), 'Create a league'),
        h('a', { class: 'btn', href: '/live', target: '_blank', rel: 'noopener' }, 'See the bay screen')))));
    state.view = {};
    return;
  }

  const d = ov.rounds_7d - ov.rounds_prev_7d;
  const delta = d === 0
    ? h('span', {}, 'Same as the week before')
    : h('span', { class: `delta ${d > 0 ? 'up' : 'down'}` }, h('span', { html: d > 0 ? ICONS.arrowUp : ICONS.arrowDown }), `${Math.abs(d)}`, h('span', { class: 'faint', style: { fontWeight: 500 } }, ' vs the week before'));
  const avg = ov.avg_vs_par_30d;
  const mix = ov.scoring_mix;

  const liveHost = h('div', {});
  const drawLive = (board) => {
    const rows = board?.players || [];
    liveHost.replaceChildren(card('Live now', board?.league_name ? `${board.league_name} · ${board.ranking === 'net' ? 'Net' : 'Gross'} to par` : 'Tonight’s leaders',
      h('div', { class: 'live-list' }, rows.length ? rows.slice(0, 6).map((p) => h('div', { class: 'live-item' },
        h('div', { class: `rk ${p.rank === 1 ? 'first' : ''}` }, p.tied ? `T${p.rank}` : p.rank),
        person(p.name, [p.team, p.thru >= board.holes_total ? 'Finished' : `Thru ${p.thru}`].filter(Boolean).join(' · ')),
        parChip(p.vs_par)))
        : h('div', { style: { padding: '8px 20px 22px' } }, emptyState('live', 'No round in progress', 'When players start entering scores, the leaders show up here live.'))),
      h('a', { class: 'btn ghost', href: active[0] ? `/live?league=${active[0].id}` : '/live', target: '_blank', rel: 'noopener' }, 'Open board', icon('external'))));
  };
  drawLive(null);

  const accuracyHost = h('div', {});
  get('/api/admin/accuracy', { days: 30 }).then(({ summary }) => {
    if (state.page !== 'overview') return;
    accuracyHost.replaceChildren(card('Capture accuracy', 'Screen capture vs the scores players entered · 30 days',
      h('div', { class: 'card-b', style: { display: 'grid', gap: '10px' } },
        summary.pairs
          ? h('div', {}, h('div', { class: 'value', style: { font: '760 34px/1 var(--font-display)' } }, `${Math.round(summary.hole_accuracy * 100)}%`),
            h('div', { class: 'faint', style: { marginTop: '6px', fontSize: '12.5px' } }, `${summary.holes_matching} of ${summary.holes_compared} holes match across ${plural(summary.pairs, 'round')}`))
          : h('p', { class: 'muted' }, 'Nothing to compare yet. It fills in once the engine reads a round that a player also entered by hand.')),
      h('a', { class: 'btn ghost', href: '#/capture' }, 'See the details')));
  }).catch(() => {});

  els.view.replaceChildren(
    h('div', { class: 'kpis' },
      kpi('Rounds this week', fmtNumber(ov.rounds_7d), delta),
      kpi('Active players', fmtNumber(ov.players_7d), `${fmtNumber(ov.players)} signed up`),
      kpi('Playing now', fmtNumber(ov.playing_now), `${plural(ov.leagues, 'league')} running`),
      kpi('Average to par', h('span', { class: parClass(avg == null ? null : Math.round(avg)) }, avg == null ? '–' : toPar(avg)), 'Completed rounds, last 30 days')),
    h('div', { class: 'grid-2' },
      h('div', { class: 'stack-col' },
        card('Rounds per day', 'Last 14 days', h('div', { class: 'card-b' }, barChart(ov.rounds_by_day.map((x) => ({ label: fmtDay(`${x.date}T12:00:00`), value: x.rounds, title: `${fmtDay(`${x.date}T12:00:00`)}: ${plural(x.rounds, 'round')}` }))))),
        card('Scoring mix', 'Every hole entered, last 30 days', h('div', { class: 'card-b' }, stackedBar([
          { label: 'Eagle or better', value: mix.eagle_or_better, color: 'var(--gold)' },
          { label: 'Birdie', value: mix.birdie, color: 'var(--under)' },
          { label: 'Par', value: mix.par, color: 'var(--ok)' },
          { label: 'Bogey', value: mix.bogey, color: 'var(--over)' },
          { label: 'Double or worse', value: mix.double_or_worse, color: 'var(--text-3)' },
        ])))),
      h('div', { class: 'stack-col' }, liveHost, accuracyHost)));

  const league = active[0];
  state.view = { refresh: renderOverview, cleanup: league ? subscribe(({ leaderboard }) => drawLive(leaderboard), () => {}, { league: league.id }) : null };
}

// ================================================================ captured rounds
// What the screen-capture engine logged (data/rounds.jsonl). Separate from the hand-entered rounds.

function capturedTable(rows) {
  if (!rows.length) return emptyState('rounds', 'No rounds match', 'Try a different filter.');
  return h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', {}, 'When'), h('th', { class: 'hide-sm' }, 'Course'),
      h('th', { class: 'num' }, 'Holes'), h('th', { class: 'num' }, 'Gross'), h('th', { class: 'num' }, 'To par'),
      h('th', {}, 'Status'), h('th', { class: 'hide-sm' }, 'Scores'))),
    h('tbody', {}, rows.map((r) => {
      const open = () => { location.hash = `#/captured/${encodeURIComponent(r.round_id)}/${encodeURIComponent(r.player)}`; };
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

async function renderCaptured() {
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
    if (state.page !== 'captured') return;
    f.rows = append ? f.rows.concat(res.rounds) : res.rounds;
    f.total = res.total;
    tableHost.replaceChildren(capturedTable(f.rows));
    countEl.textContent = `${fmtNumber(f.total)} ${f.total === 1 ? 'round' : 'rounds'}`;
    moreBtn.hidden = f.rows.length >= f.total;
  }

  els.view.replaceChildren(
    h('div', { class: 'callout info' }, icon('camera'), h('div', {}, h('b', {}, 'Rounds the engine read from GSPro. '),
      'These come from screen capture, not from players. Use Capture accuracy to see how well they match what players enter by hand.')),
    h('section', { class: 'card' },
      h('div', { class: 'toolbar' }, h('div', { class: 'chips' }, chips), h('div', { class: 'grow' }), countEl,
        h('label', { class: 'search' }, h('span', { html: ICONS.search }), search)),
      tableHost,
      h('div', { style: { padding: '14px 20px 18px', display: 'flex', justifyContent: 'center' } }, moreBtn)));
  state.view = { refresh: () => load(false) };
  await load(false);
}

async function showCapturedRound(roundId, player) {
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
  els.drawerBody.replaceChildren(...[
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
  ].filter(Boolean));
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
      card('Current round (screen capture)', null, h('div', { class: 'card-b' }, round.in_progress
        ? h('div', { style: { display: 'grid', gap: '12px' } }, ...round.players.map((p) => h('div', { class: 'person' }, avatar(p.name), h('div', { style: { flex: 1, minWidth: 0 } },
          h('div', { class: 'n' }, p.name), h('div', { class: 'bar', style: { marginTop: '6px' } }, h('i', { style: { width: `${Math.min(100, (p.holes / 9) * 100)}%` } }))),
        h('span', { class: 'badge' }, `${plural(p.holes, 'hole')} played`))),
        h('p', { class: 'faint', style: { fontSize: '12.5px' } }, `${plural(round.shots, 'shot')} tracked · idle ${Math.round((round.idle_seconds || 0) / 60)} min of ${round.idle_timeout_minutes} before an abandoned round is saved`))
        : h('p', { class: 'muted' }, 'No round in progress.')))),
    h('div', { class: 'stack-col' },
      card('Bay screen link', 'Put this on any bay screen', h('div', { class: 'card-b', style: { display: 'grid', gap: '12px' } },
        h('div', { class: 'callout' }, h('code', { style: { wordBreak: 'break-all' } }, url)),
        h('div', { style: { display: 'flex', gap: '8px' } },
          h('a', { class: 'btn primary', href: '/live', target: '_blank', rel: 'noopener' }, icon('live'), 'Open'),
          h('button', { class: 'btn', onclick: async () => { try { await navigator.clipboard.writeText(url); toast('Link copied'); } catch { toast('Copy failed – select the link instead'); } } }, icon('copy'), 'Copy link')),
        h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'The first time a screen opens it asks which league to show and remembers; add ', h('code', {}, '?league=ID'), ' to pin it. For screens on other PCs and for phones, start the web UI with ', h('code', {}, '--host 0.0.0.0'), ' and use this PC’s network address – on a trusted venue network.'))),
      card('Launch-monitor feed', null, h('div', { class: 'card-b' }, e.feed?.configured
        ? h('p', {}, `Connected to ${e.feed.host}:${e.feed.port}.`)
        : h('p', { class: 'muted' }, 'Not connected. Rounds are tracked from the GSPro screen; shot data (ball speed, carry) needs the launch-monitor feed.'))),
      card('About', null, h('div', { class: 'card-b' }, h('dl', { class: 'kv' },
        h('dt', {}, 'Version'), h('dd', {}, state.version || '–'),
        h('dt', {}, 'Data'), h('dd', {}, state.demo ? 'Demo venue (fictional)' : 'Your venue'),
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

const pages = makePages({
  els, state, openDrawer, closeDrawer, drawerBody: () => els.drawerBody, route: () => route(true),
});

async function route(force = false) {
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const head = parts[0];
  const id = head === 'round' ? 'leagues' : (TITLES[head] ? head : 'overview');
  const pageKey = head === 'leagues' && parts[1] ? `leagues/${parts[1]}` : id;

  if (!isDrawerRoute()) state.baseHash = `#/${pageKey}`;
  else if (state.pageKey === null) state.baseHash = `#/${id}`;   // opened a link straight to a drawer

  if (force || state.pageKey !== pageKey) {
    state.view?.cleanup?.();
    state.page = id;
    state.pageKey = pageKey;
    state.view = null;
    setNavCurrent(id);
    els.view.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    try {
      if (id === 'overview') await renderOverview();
      else if (id === 'leagues') await (parts[1] && head === 'leagues' ? pages.renderLeague(parts[1]) : pages.renderLeagues());
      else if (id === 'players') await pages.renderPlayers();
      else if (id === 'capture') await pages.renderCapture();
      else if (id === 'captured') await renderCaptured();
      else renderSystem();
    } catch (err) {
      if (err.status === 401 || err.status === 403) { goToLogin(); return; }
      if (state.pageKey === pageKey) els.view.replaceChildren(card(null, null, emptyState('alert', 'Something went wrong', `${err.message}. Is the server still running?`)));
    }
  }

  if (head === 'round' && parts[1]) pages.showRound(parts[1]);
  else if (head === 'players' && parts[1]) pages.showPlayer(parts[1]);
  else if (head === 'capture' && parts[1]) pages.showComparison(parts[1]);
  else if (head === 'captured' && parts[1] && parts[2]) showCapturedRound(parts[1], parts.slice(2).join('/'));
  else closeDrawer(false);
}

// ======================================================================= status

function updateChrome() {
  const e = state.engine;
  els.demoFlag.hidden = !state.demo;
  els.mode.textContent = state.demo ? 'Demo data' : 'Live data';
  els.version.textContent = state.version ? `Version ${state.version}` : '';
  if (state.me) els.userName.textContent = state.me.display_name;

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
  state.engine = engine;
  state.demo = Boolean(leaderboard?.demo || engine?.demo);
  updateChrome();
  state.view?.onLive?.();

  // a real log has 3 file stamps; refetch the captured-rounds list only when the round log itself changed
  const version = Array.isArray(signature) && signature.length >= 3 ? signature[2] : undefined;
  if (version !== undefined && state.roundsVersion !== undefined && version !== state.roundsVersion && state.page === 'captured') state.view?.refresh?.();
  state.roundsVersion = version;
}

// ========================================================================= start

(async function start() {
  let s;
  try { s = await session(); } catch { document.getElementById('root').textContent = 'Can’t reach the server.'; return; }
  if (!s.user) { goToLogin(); return; }
  if (s.user.role !== 'admin') { location.replace('/app'); return; }
  state.me = s.user;
  state.demo = Boolean(s.demo);
  buildShell();
  updateChrome();
  get('/api/health').then((hlth) => { state.version = hlth.version; state.demo ||= hlth.mode === 'demo'; updateChrome(); }).catch(() => {});
  subscribe(onLive, (conn) => { state.conn = conn; updateChrome(); });
  window.addEventListener('hashchange', () => route());
  setInterval(() => { if (!document.hidden) state.view?.refresh?.(); }, 60000);   // keep relative times ("5 min ago") honest
  route();
}());
