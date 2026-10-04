// The player app: a small hash-routed single page app (no build step, no framework).
//   #/home   #/play   #/play/<round>   #/rounds   #/rounds/<round>   #/leagues   #/leagues/<id>   #/handicap   #/profile

import { h, clear, ICONS, LOGO, toPar, parClass, avatar, fmtDateTime, fmtDay, plural } from './dom.js';
import { get, post, put, patch, session, subscribe, goToLogin, logout } from './api.js';
import { lineChart, sparkline } from './charts.js';
import { scorecard } from './scorecard.js';
import {
  icon, parChip, statusBadge, card, kpi, emptyState, loading, toast, person, themeButton, fmtIndex, manualHoles, field, confirmAction,
} from './ui.js';

const NAV = [
  { id: 'home', label: 'Home', icon: 'home' },
  { id: 'play', label: 'Play', icon: 'flag' },
  { id: 'rounds', label: 'Rounds', icon: 'rounds' },
  { id: 'leagues', label: 'Leagues', icon: 'leagues' },
  { id: 'handicap', label: 'Handicap', icon: 'trend' },
  { id: 'profile', label: 'Profile', icon: 'user' },
];
const TABS = ['home', 'play', 'rounds', 'leagues', 'profile'];   // the five that fit on a phone's bottom bar
const TITLES = Object.fromEntries(NAV.map((n) => [n.id, n.label]));

const state = { me: null, home: null, demo: false, page: null, cleanup: null };
const els = {};

// ==================================================================== data

async function loadHome() {
  state.home = await get('/api/me/home');
  state.me = state.home.user;
  return state.home;
}

const leagueName = (id) => state.home?.leagues.find((l) => l.id === id)?.name || null;
const hasLeagues = () => (state.home?.leagues.length || 0) > 0;

function rememberBay(value) { try { localStorage.setItem('sc22.bay', value); } catch { /* not remembered */ } }
function lastBay() { try { return localStorage.getItem('sc22.bay') || ''; } catch { return ''; } }

// ==================================================================== shell

function buildShell() {
  els.title = h('h1', {}, '');
  els.demo = h('span', { class: 'badge demo-flag', hidden: true }, 'Demo');
  els.view = h('main', { class: 'content', id: 'view', tabindex: '-1' });
  els.menuBtn = h('button', { class: 'btn icon ghost menu-btn', 'aria-label': 'Open menu', html: ICONS.menu, onclick: () => els.app.classList.toggle('nav-open') });
  els.liveLink = h('a', { href: '/live', target: '_blank', rel: 'noopener' }, icon('live'), 'Live leaderboard', h('span', { class: 'ext', html: ICONS.external }));
  els.adminLink = h('a', { href: '/admin' }, icon('system'), 'Venue admin', h('span', { class: 'ext', html: ICONS.external }));

  els.nav = h('nav', { class: 'nav', 'aria-label': 'Main' },
    NAV.map((n) => h('a', { href: `#/${n.id}`, 'data-id': n.id, onclick: () => els.app.classList.remove('nav-open') }, icon(n.icon), n.label)),
    h('div', { class: 'sep' }), els.liveLink, els.adminLink);

  els.userName = h('div', { class: 'n' }, '');
  els.userSub = h('div', { class: 's' }, '');
  els.avatarSlot = h('span', {});
  els.bottom = h('nav', { class: 'bottom-nav', 'aria-label': 'Main' },
    TABS.map((id) => {
      const n = NAV.find((x) => x.id === id);
      return h('a', { href: `#/${id}`, 'data-id': id }, icon(n.icon), n.label);
    }));

  els.app = h('div', { class: 'app' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('span', { html: LOGO }), h('div', {}, 'SimCore22', h('small', {}, 'Player'))),
      els.nav,
      h('div', { class: 'side-foot' },
        h('div', { class: 'side-user' }, els.avatarSlot, h('div', { style: { minWidth: 0 } }, els.userName, els.userSub)),
        h('button', { class: 'btn ghost', onclick: logout }, icon('logout'), 'Log out'))),
    h('div', { class: 'main' },
      h('header', { class: 'top' }, els.menuBtn, els.title, h('div', { class: 'grow' }), els.demo, themeButton()),
      els.view),
    els.bottom);
  clear(document.getElementById('root')).append(els.app);
}

function updateChrome() {
  const me = state.me;
  els.userName.textContent = me.display_name;
  els.userSub.textContent = me.role === 'admin' ? 'Venue admin' : `Index ${fmtIndex(me.indoor_index)}`;
  els.avatarSlot.replaceChildren(avatar(me.display_name));
  els.adminLink.hidden = me.role !== 'admin';
  els.demo.hidden = !state.demo;
  const first = state.home?.leagues[0];
  els.liveLink.href = first ? `/live?league=${first.id}` : '/live';
}

function setCurrent(id) {
  document.querySelectorAll('[data-id]').forEach((a) => (a.dataset.id === id ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  els.title.textContent = TITLES[id] || '';
  document.title = `${TITLES[id] || 'Player'} · SimCore22`;
}

function nameOf(round) { return round.league_id ? leagueName(round.league_id) || 'League round' : 'Casual round'; }

// ==================================================================== home

async function renderHome() {
  els.view.replaceChildren(card(null, null, loading(5)));
  const home = await loadHome();
  if (state.page !== 'home') return;
  updateChrome();

  const { stats, handicap, active_round: active } = home;
  const done = home.rounds.filter((r) => r.status === 'completed' || r.status === 'ended_early');
  const first = home.user.display_name.split(' ')[0];

  const banner = active
    ? h('div', { class: 'banner' },
      h('div', { class: 'grow' }, h('h2', {}, 'Round in progress'),
        h('p', {}, `${nameOf(active)}${active.bay ? ` · ${active.bay}` : ''} · ${active.thru} of ${active.holes_total} holes entered${active.vs_par != null ? ` · ${toPar(active.vs_par)}` : ''}`)),
      h('a', { class: 'btn primary big', href: '#/play' }, 'Continue round'))
    : h('div', { class: 'banner' },
      h('div', { class: 'grow' }, h('h2', {}, 'Ready to play?'), h('p', {}, 'Enter each hole as you finish it – your league’s leaderboard updates live.')),
      h('a', { class: 'btn primary big', href: '#/play' }, 'Start a round'));

  const leagueCards = home.leagues.length
    ? h('div', { class: 'live-list' }, home.leagues.map((l) => h('div', { class: 'live-item', style: { gridTemplateColumns: 'minmax(0,1fr) auto' } },
      h('div', {}, h('div', { class: 'n', style: { fontWeight: 650 } }, l.name),
        h('div', { class: 'sub' }, [l.season, `${l.holes} holes`, l.ranking === 'net' ? 'Net' : 'Gross', plural(l.members, 'player')].filter(Boolean).join(' · '))),
      h('div', { style: { display: 'flex', gap: '8px' } },
        h('a', { class: 'btn', href: `#/leagues/${l.id}` }, 'Table'),
        h('a', { class: 'btn ghost', href: `/live?league=${l.id}`, target: '_blank', rel: 'noopener' }, 'Live board')))))
    : h('div', { class: 'card-b' }, emptyState('leagues', 'No league yet', 'Ask your venue for a join code, or play a casual round any time.'));

  const joinInput = h('input', { class: 'input', placeholder: 'Join code', maxlength: 8, autocapitalize: 'characters', 'aria-label': 'League join code', style: { textTransform: 'uppercase' } });
  const joinError = h('div', { class: 'form-error', hidden: true, role: 'alert' });
  const join = async (event) => {
    event.preventDefault();
    joinError.hidden = true;
    try { const l = await post('/api/leagues/join', { code: joinInput.value }); toast(`Joined ${l.name}`); renderHome(); }
    catch (err) { joinError.textContent = err.message; joinError.hidden = false; }
  };

  const recent = done.slice(0, 5);
  els.view.replaceChildren(
    h('div', { class: 'hello' }, h('div', {}, h('h2', {}, `Hi, ${first}`), h('p', {}, 'Here’s where you stand.'))),
    banner,
    h('div', { class: 'kpis' },
      kpi('Indoor handicap', fmtIndex(handicap.index), handicap.history.length > 1
        ? `${plural(handicap.history.filter((x) => x.round_id).length, 'round')} counted`
        : handicap.outdoor_index != null ? `Starts from your outdoor ${fmtIndex(handicap.outdoor_index)}` : 'Play a round to get one'),
      kpi('Rounds played', stats.rounds, 'Completed or ended early'),
      kpi('Average to par', h('span', { class: parClass(stats.avg_vs_par == null ? null : Math.round(stats.avg_vs_par)) }, stats.avg_vs_par == null ? '–' : toPar(Math.round(stats.avg_vs_par * 10) / 10)), 'Completed rounds'),
      kpi('Best round', h('span', { class: parClass(stats.best_vs_par) }, toPar(stats.best_vs_par)), 'Score to par')),
    h('div', { class: 'grid-2' },
      h('div', { class: 'stack-col' },
        card('Recent rounds', 'Click one for the scorecard',
          done.length ? h('div', { class: 'card-b flush table-wrap' }, roundsTable(recent)) : h('div', { class: 'card-b' }, emptyState('rounds', 'No rounds yet', 'Your first round will show up here.')),
          done.length ? h('a', { class: 'btn ghost', href: '#/rounds' }, 'All rounds') : null),
        card('Indoor handicap', 'How it has moved', h('div', { class: 'card-b' }, handicapChart(handicap)),
          h('a', { class: 'btn ghost', href: '#/handicap' }, 'How it works'))),
      h('div', { class: 'stack-col' },
        card('My leagues', null, leagueCards),
        card('Join a league', 'Enter the code from your venue', h('form', { class: 'card-b form', onsubmit: join },
          h('div', { style: { display: 'flex', gap: '8px' } }, joinInput, h('button', { class: 'btn primary', type: 'submit' }, 'Join')), joinError)))));
  state.cleanup = null;
}

function handicapChart(handicap) {
  const points = handicap.history.filter((x) => x.index != null).map((x) => ({ label: fmtDay(x.at), value: x.index }));
  return points.length >= 2
    ? lineChart(points, { format: (v) => (v === 0 ? '0' : String(v)) })
    : h('p', { class: 'muted', style: { padding: '8px 0' } }, 'Your handicap chart appears after your first couple of rounds.');
}

// ==================================================================== rounds

function roundsTable(rows) {
  return h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', { class: 'hide-sm' }, 'Where'), h('th', { class: 'num' }, 'Holes'),
      h('th', { class: 'num' }, 'Gross'), h('th', { class: 'num' }, 'To par'), h('th', { class: 'hide-sm' }, 'Status'))),
    h('tbody', {}, rows.map((r) => {
      const open = () => { location.hash = `#/rounds/${r.id}`; };
      return h('tr', { class: 'click', tabindex: 0, role: 'link', onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); } },
        h('td', { class: 'nowrap' }, fmtDateTime(r.started_at)),
        h('td', { class: 'muted hide-sm' }, nameOf(r)),
        h('td', { class: 'num' }, `${r.thru}/${r.holes_total}`),
        h('td', { class: 'num' }, r.gross ?? '–'),
        h('td', { class: 'num' }, parChip(r.vs_par)),
        h('td', { class: 'hide-sm' }, statusBadge(r.status)));
    })));
}

async function renderRounds() {
  els.view.replaceChildren(card(null, null, loading(6)));
  const { rounds } = await loadHome();
  if (state.page !== 'rounds') return;
  const shown = rounds.filter((r) => r.thru > 0 || r.status === 'in_progress');
  els.view.replaceChildren(card(null, null, shown.length
    ? h('div', { class: 'card-b flush table-wrap' }, roundsTable(shown))
    : emptyState('rounds', 'No rounds yet', 'Rounds you enter show up here.', h('a', { class: 'btn primary', href: '#/play' }, 'Start a round'))));
}

async function renderRoundDetail(id) {
  els.view.replaceChildren(card(null, null, loading(5)));
  let round;
  try { round = await get(`/api/play/rounds/${id}`); } catch (err) {
    els.view.replaceChildren(card(null, null, emptyState('alert', 'Round not found', err.message, h('a', { class: 'btn', href: '#/rounds' }, 'Back to rounds'))));
    return;
  }
  if (state.page !== 'rounds') return;
  const sc = scorecard(manualHoles(round));
  const net = round.course_handicap > 0;
  els.view.replaceChildren(
    h('div', { class: 'hello' }, h('div', {}, h('h2', {}, nameOf(round)),
      h('p', {}, [round.course_name, round.bay, fmtDateTime(round.started_at)].filter(Boolean).join(' · '))),
    h('div', { style: { display: 'flex', gap: '8px' } },
      h('a', { class: 'btn', href: '#/rounds' }, 'All rounds'),
      h('a', { class: 'btn primary', href: `#/play/${round.id}` }, round.status === 'in_progress' ? 'Continue' : 'Edit scores'))),
    h('div', { class: 'stat-band', style: { gridTemplateColumns: net ? '1.3fr 1fr 1fr 1fr' : '1.3fr 1fr 1fr' } },
      h('div', {}, h('div', { class: 'label' }, 'To par'), h('div', { class: `value ${parClass(round.vs_par)}` }, toPar(round.vs_par))),
      h('div', {}, h('div', { class: 'label' }, 'Gross'), h('div', { class: 'value' }, round.gross ?? '–')),
      h('div', {}, h('div', { class: 'label' }, 'Holes'), h('div', { class: 'value' }, `${round.thru}/${round.holes_total}`)),
      net ? h('div', {}, h('div', { class: 'label' }, 'Net'), h('div', { class: 'value' }, round.net ?? '–')) : null),
    h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, statusBadge(round.status),
      round.counts ? h('span', { class: 'badge ok' }, 'Counts toward handicap') : h('span', { class: 'badge muted' }, 'Not counted for handicap'),
      round.differential != null ? h('span', { class: 'badge' }, `Differential ${round.differential.toFixed(1)}`) : null),
    card('Scorecard', null, h('div', { class: 'card-b' }, sc.element)));
  state.cleanup = null;
}

// ================================================================= play (entry)

function renderStart() {
  const home = state.home;
  const leagues = home.leagues;
  const league = h('select', { class: 'select', name: 'league', 'aria-label': 'League' },
    leagues.map((l) => h('option', { value: String(l.id) }, `${l.name} (${l.holes} holes)`)),
    h('option', { value: '' }, 'Casual round – no league'));
  const holes = h('select', { class: 'select', name: 'holes' }, h('option', { value: '9' }, '9 holes'), h('option', { value: '18' }, '18 holes'));
  const bay = h('input', { class: 'input', name: 'bay', placeholder: 'e.g. Bay 3', maxlength: 20, value: lastBay() });
  const course = h('input', { class: 'input', name: 'course', placeholder: 'optional', maxlength: 60 });
  const casualOnly = h('div', { class: 'two' }, field('Holes', holes), field('Course', course));
  const error = h('div', { class: 'form-error', hidden: true, role: 'alert' });
  const sync = () => { casualOnly.hidden = league.value !== ''; };
  league.addEventListener('change', sync);
  sync();

  const form = h('form', { class: 'card-b form', style: { maxWidth: '520px' }, onsubmit: async (event) => {
    event.preventDefault();
    error.hidden = true;
    rememberBay(bay.value);
    try {
      const body = league.value ? { league_id: Number(league.value), bay: bay.value } : { holes: Number(holes.value), bay: bay.value, course_name: course.value };
      const round = await post('/api/play/rounds', body);
      toast('Round started – good luck!');
      history.replaceState(null, '', `#/play/${round.id}`);
      route();
    } catch (err) { error.textContent = err.message; error.hidden = false; }
  } },
  field('Playing in', league, leagues.length ? null : 'You’re not in a league yet – this will be a casual round. Join one from Home.'),
  casualOnly,
  field('Bay', bay, 'So the front desk can see who is where.'),
  error,
  h('button', { class: 'btn primary big', type: 'submit' }, 'Start round'));

  els.view.replaceChildren(card('Start a round', 'Then enter each hole as you finish it', form));
}

async function renderPlay(roundId) {
  els.view.replaceChildren(card(null, null, loading(5)));
  let round;
  if (roundId) {
    try { round = await get(`/api/play/rounds/${roundId}`); } catch (err) {
      els.view.replaceChildren(card(null, null, emptyState('alert', 'Round not found', err.message, h('a', { class: 'btn', href: '#/play' }, 'Back'))));
      return;
    }
  } else {
    const home = await loadHome();
    updateChrome();
    round = home.active_round;
  }
  if (state.page !== 'play') return;
  if (!round) { await loadHome(); updateChrome(); renderStart(); return; }
  renderEntry(round);
}

function firstOpenHole(round) {
  const open = round.holes.find((x) => x.strokes == null);
  return open ? open.hole : (round.status === 'in_progress' ? round.holes_total : 1);
}

function renderEntry(initial) {
  const s = { round: initial, current: firstOpenHole(initial), value: 4, par: null, busy: false, board: null, summary: false };
  const casual = !initial.league_id;
  const boardHost = h('div', {});
  const host = h('div', { class: 'stack-col' });
  els.view.replaceChildren(host);

  const holeInfo = () => s.round.holes.find((x) => x.hole === s.current);
  const resetValue = () => { const hole = holeInfo(); s.value = hole.strokes ?? hole.par; s.par = hole.par; };
  resetValue();

  const label = (diff) => ({ '-3': 'Albatross', '-2': 'Eagle', '-1': 'Birdie', 0: 'Par', 1: 'Bogey', 2: 'Double bogey', 3: 'Triple bogey' }[diff] || (diff < -3 ? 'Incredible' : `+${diff}`));

  async function save() {
    if (s.busy) return;
    s.busy = true;
    try {
      const body = { strokes: s.value };
      if (casual) body.par = s.par;
      s.round = await put(`/api/play/rounds/${s.round.id}/holes/${s.current}`, body);
      if (s.round.status !== 'in_progress' && s.round.thru === s.round.holes_total && initial.status === 'in_progress') { s.summary = true; await loadHome(); updateChrome(); }
      else if (s.round.status === 'in_progress') {
        const next = s.round.holes.find((x) => x.strokes == null && x.hole > s.current) || s.round.holes.find((x) => x.strokes == null);
        s.current = next ? next.hole : s.current;
      }
      resetValue();
    } catch (err) { toast(err.message); } finally { s.busy = false; draw(); }
  }

  async function endRound() {
    const entered = s.round.thru;
    const text = entered === 0 ? 'No holes entered yet. Cancel this round?'
      : `End the round after ${plural(entered, 'hole')}? What you’ve entered is saved${entered >= 9 ? ' and counts toward your handicap' : ' (a round needs 9 holes to count toward your handicap)'}.`;
    if (!confirmAction(text)) return;
    try { s.round = await post(`/api/play/rounds/${s.round.id}/finish`); await loadHome(); updateChrome(); s.summary = s.round.status !== 'abandoned'; if (!s.summary) { location.hash = '#/home'; return; } draw(); }
    catch (err) { toast(err.message); }
  }

  const goto = (n) => { s.current = n; resetValue(); draw(); };
  const bump = (d) => { s.value = Math.max(1, Math.min(15, s.value + d)); draw(); };

  function chips() {
    return h('div', { class: 'hole-chips', role: 'group', 'aria-label': 'Holes' }, s.round.holes.map((x) => {
      const tone = x.strokes == null ? '' : x.strokes < x.par ? 'under' : x.strokes > x.par ? 'over' : '';
      return h('button', { type: 'button', class: `hole-chip ${x.strokes != null ? 'done' : ''} ${tone}`, 'aria-current': x.hole === s.current ? 'true' : null,
        'aria-label': `Hole ${x.hole}, par ${x.par}${x.strokes != null ? `, ${x.strokes} strokes` : ', not entered'}`, onclick: () => goto(x.hole) },
      h('small', {}, x.hole), h('b', {}, x.strokes ?? '·'));
    }));
  }

  function totals() {
    const r = s.round;
    const showNet = r.course_handicap > 0;
    return h('div', { class: 'totals', style: showNet ? null : { gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' } },
      h('div', {}, h('div', { class: 'label' }, 'Thru'), h('div', { class: 'value' }, `${r.thru}/${r.holes_total}`)),
      h('div', {}, h('div', { class: 'label' }, 'Gross'), h('div', { class: 'value' }, r.gross ?? '–')),
      h('div', {}, h('div', { class: 'label' }, 'To par'), h('div', { class: `value ${parClass(r.vs_par)}` }, toPar(r.vs_par))),
      showNet ? h('div', {}, h('div', { class: 'label' }, `Net (${r.course_handicap} strokes)`), h('div', { class: `value ${parClass(r.net_vs_par)}` }, toPar(r.net_vs_par))) : null);
  }

  function entryCard() {
    const hole = holeInfo();
    const par = casual ? s.par : hole.par;
    const diff = s.value - par;
    const parSelect = casual
      ? h('select', { 'aria-label': 'Par', onchange: (e) => { s.par = Number(e.target.value); if (hole.strokes == null) s.value = s.par; draw(); } },
        [3, 4, 5, 6].map((p) => h('option', { value: p, selected: p === par ? '' : null }, p)))
      : null;
    const quick = [[-2, 'Eagle'], [-1, 'Birdie'], [0, 'Par'], [1, 'Bogey'], [2, 'Double']]
      .map(([d, name]) => [d, name, par + d]).filter(([, , v]) => v >= 1)
      .map(([d, name, v]) => h('button', { type: 'button', class: 'chip', 'aria-pressed': d === diff ? 'true' : 'false', onclick: () => { s.value = v; draw(); } }, `${name} ${v}`));

    const saved = hole.strokes != null;
    return h('section', { class: 'card hole-card' },
      h('div', { class: 'hole-title' },
        h('h2', {}, `Hole ${s.current}`),
        h('span', { class: 'par' }, 'Par ', parSelect || par),
        hole.received ? h('span', { class: 'recv' }, `+${hole.received} stroke${hole.received > 1 ? 's' : ''} for you`) : null),
      h('div', { class: 'stepper' },
        h('button', { type: 'button', class: 'step-btn', 'aria-label': 'One fewer stroke', html: ICONS.minus, onclick: () => bump(-1) }),
        h('div', { class: `val ${parClass(diff)}`, role: 'status', 'aria-live': 'polite', 'aria-label': `${s.value} strokes` }, s.value),
        h('button', { type: 'button', class: 'step-btn', 'aria-label': 'One more stroke', html: ICONS.plus, onclick: () => bump(1) })),
      h('div', { class: 'value-label' }, s.value === 1 ? 'Hole in one!' : label(diff)),
      h('div', { class: 'quick' }, quick),
      h('div', { class: 'entry-actions' },
        s.current > 1 ? h('button', { type: 'button', class: 'btn big', onclick: () => goto(s.current - 1) }, 'Back') : null,
        h('button', { type: 'button', class: 'btn primary big', disabled: s.busy ? '' : null, onclick: save },
          saved ? 'Update hole' : s.round.thru + 1 >= s.round.holes_total ? 'Save & finish' : 'Save hole')));
  }

  function summary() {
    const r = s.round;
    return card(null, null, h('div', { class: 'done-card' },
      h('div', { class: 'ring', html: ICONS.check }),
      h('h2', {}, r.status === 'completed' ? 'Round complete' : 'Round saved'),
      h('div', { class: `big ${parClass(r.vs_par)}` }, toPar(r.vs_par)),
      h('p', { class: 'muted' }, `${r.gross} strokes over ${plural(r.thru, 'hole')}${r.course_handicap > 0 ? ` · net ${toPar(r.net_vs_par)}` : ''}`),
      state.me.indoor_index != null ? h('p', {}, 'Your indoor handicap is now ', h('b', {}, fmtIndex(state.me.indoor_index))) : null,
      h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' } },
        h('a', { class: 'btn primary big', href: `#/rounds/${r.id}` }, 'See scorecard'),
        h('a', { class: 'btn big', href: '#/home' }, 'Home'))));
  }

  function draw() {
    if (s.summary) { host.replaceChildren(summary()); return; }
    const r = s.round;
    const finished = r.status !== 'in_progress';
    host.replaceChildren(
      h('div', { class: 'hello' },
        h('div', {}, h('h2', {}, nameOf(r)), h('p', {}, [r.course_name, r.bay, `${r.holes_total} holes`, r.course_handicap > 0 ? `${r.course_handicap} strokes` : null].filter(Boolean).join(' · '))),
        h('div', { style: { display: 'flex', gap: '8px' } },
          finished ? h('a', { class: 'btn', href: `#/rounds/${r.id}` }, 'Done') : h('button', { class: 'btn danger', type: 'button', onclick: endRound }, 'End round'))),
      h('div', { class: 'callout info', hidden: finished ? null : true }, icon('alert'), h('div', {}, h('b', {}, 'Editing a finished round. '), 'Changes update your handicap straight away.')),
      h('div', { class: 'entry' },
        h('div', { class: 'entry-main' }, chips(), entryCard(), totals()),
        r.league_id ? h('div', { class: 'stack-col' }, boardHost) : null));
    drawBoard();
  }

  function drawBoard() {
    const r = s.round;
    if (!r.league_id) return;
    const board = s.board;
    const rows = board?.players || [];
    const myName = state.me.display_name;
    const top = rows.slice(0, 6);
    const mine = rows.find((p) => p.name === myName);
    const shown = mine && !top.includes(mine) ? [...top, mine] : top;
    boardHost.replaceChildren(card('Live leaderboard', board ? `${board.league_name} · ${board.ranking === 'net' ? 'Net' : 'Gross'} to par` : 'Connecting…',
      rows.length ? h('div', {}, shown.map((p) => h('div', { class: `minirow ${p.name === myName ? 'me' : ''}` },
        h('div', { class: `rk ${p.rank === 1 ? 'first' : ''}` }, p.tied ? `T${p.rank}` : p.rank),
        person(p.name, p.bay || null),
        h('span', { class: 'thru' }, p.thru >= board.holes_total ? 'F' : `Thru ${p.thru}`),
        parChip(p.vs_par))))
        : h('div', { class: 'card-b' }, h('p', { class: 'muted' }, 'Scores appear here as people enter their first hole.')),
      h('a', { class: 'btn ghost', href: `/live?league=${r.league_id}`, target: '_blank', rel: 'noopener' }, 'Open', icon('external'))));
  }

  draw();
  if (initial.league_id) {
    const stop = subscribe(({ leaderboard }) => { s.board = leaderboard; drawBoard(); }, () => {}, { league: initial.league_id });
    state.cleanup = stop;
  }
}

// ================================================================== leagues

async function renderLeagues() {
  els.view.replaceChildren(card(null, null, loading(4)));
  const home = await loadHome();
  if (state.page !== 'leagues') return;
  if (home.leagues.length === 1) { location.replace(`#/leagues/${home.leagues[0].id}`); return; }
  els.view.replaceChildren(card(null, null, home.leagues.length
    ? h('div', { class: 'live-list' }, home.leagues.map((l) => h('div', { class: 'live-item', style: { gridTemplateColumns: 'minmax(0,1fr) auto' } },
      h('div', {}, h('div', { style: { fontWeight: 650 } }, l.name), h('div', { class: 'sub' }, [l.season, `${l.holes} holes`, plural(l.members, 'player')].filter(Boolean).join(' · '))),
      h('a', { class: 'btn', href: `#/leagues/${l.id}` }, 'Open'))))
    : emptyState('leagues', 'No leagues yet', 'Ask your venue for a join code and enter it on Home.', h('a', { class: 'btn primary', href: '#/home' }, 'Go home'))));
}

async function renderLeague(id) {
  els.view.replaceChildren(card(null, null, loading(6)));
  let table;
  try { table = await get(`/api/leagues/${id}/table`); } catch (err) {
    els.view.replaceChildren(card(null, null, emptyState('alert', 'Can’t show that league', err.message, h('a', { class: 'btn', href: '#/leagues' }, 'Back'))));
    return;
  }
  if (state.page !== 'leagues') return;
  const { league, players } = table;
  const myId = state.me.id;
  const unit = league.ranking === 'net' ? 'Net' : 'Gross';
  const boardHost = h('div', {});
  const drawBoard = (board) => {
    const rows = board?.players || [];
    boardHost.replaceChildren(card('Tonight', rows.length ? `${unit} to par · live` : 'Nobody’s on the course',
      rows.length ? h('div', {}, rows.slice(0, 8).map((p) => h('div', { class: `minirow ${p.name === state.me.display_name ? 'me' : ''}` },
        h('div', { class: `rk ${p.rank === 1 ? 'first' : ''}` }, p.tied ? `T${p.rank}` : p.rank),
        person(p.name, p.bay || p.team || null),
        h('span', { class: 'thru' }, p.thru >= board.holes_total ? 'F' : `Thru ${p.thru}`),
        parChip(p.vs_par))))
        : h('div', { class: 'card-b' }, h('p', { class: 'muted' }, 'When players start entering scores they appear here live.')),
      h('a', { class: 'btn ghost', href: `/live?league=${league.id}`, target: '_blank', rel: 'noopener' }, 'Open board', icon('external'))));
  };
  drawBoard(null);

  els.view.replaceChildren(
    h('div', { class: 'hello' }, h('div', {}, h('h2', {}, league.name),
      h('p', {}, [league.season, league.course_name, `${league.holes} holes`, `${unit} scoring`].filter(Boolean).join(' · '))),
    h('a', { class: 'btn primary big', href: '#/play' }, 'Play a round')),
    h('div', { class: 'grid-2' },
      card('Standings', `Average ${unit.toLowerCase()} score to par · finished league rounds`, h('div', { class: 'card-b flush table-wrap' }, h('table', { class: 'table' },
        h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Player'), h('th', { class: 'num' }, 'Rds'), h('th', { class: 'num' }, 'Avg'), h('th', { class: 'num hide-sm' }, 'Best'),
          h('th', { class: 'num hide-sm' }, 'Index'), h('th', { class: 'hide-sm', style: { width: '90px' } }, 'Form'))),
        h('tbody', {}, players.map((p) => h('tr', { class: p.user_id === myId ? 'me' : '' },
          h('td', {}, p.rounds ? (p.tied ? `T${p.rank}` : p.rank) : '–'),
          h('td', {}, person(p.name, p.team)),
          h('td', { class: 'num' }, p.rounds),
          h('td', { class: 'num' }, p.avg_vs_par == null ? '–' : parChip(Math.round(p.avg_vs_par * 10) / 10)),
          h('td', { class: 'num hide-sm' }, p.best_vs_par == null ? '–' : toPar(p.best_vs_par)),
          h('td', { class: 'num hide-sm' }, fmtIndex(p.index)),
          h('td', { class: 'hide-sm' }, sparkline(p.trend)))))))),
      boardHost));
  state.cleanup = subscribe(({ leaderboard }) => drawBoard(leaderboard), () => {}, { league: league.id });
}

// ================================================================== handicap

async function renderHandicap() {
  els.view.replaceChildren(card(null, null, loading(5)));
  const home = await loadHome();
  if (state.page !== 'handicap') return;
  updateChrome();
  const { handicap } = home;
  const counted = home.rounds.filter((r) => r.counts).sort((a, b) => a.started_at.localeCompare(b.started_at));
  const afterByRound = new Map(handicap.history.filter((x) => x.round_id).map((x) => [x.round_id, x.index]));
  const n = counted.length;

  els.view.replaceChildren(
    h('div', { class: 'grid-2' },
      h('div', { class: 'stack-col' },
        card(null, null, h('div', { class: 'index-hero' },
          h('div', { class: 'label' }, 'Your indoor handicap'),
          h('div', { class: 'value' }, fmtIndex(handicap.index)),
          h('div', { class: 'foot' }, n >= 3 ? `Built from your best ${handicap.counted_best_of} of ${plural(Math.min(n, 20), 'recent round')}.`
            : n > 0 ? `Blended with your outdoor index until you have 3 rounds (${n} so far).`
              : handicap.outdoor_index != null ? `Your outdoor index (${fmtIndex(handicap.outdoor_index)}) until you play a round.` : 'Play a round to get one.'))),
        card('History', 'After each round · lower is better', h('div', { class: 'card-b' }, handicapChart(handicap))),
        card('Counted rounds', 'Differential = how far over par you played, scaled to 18 holes',
          n ? h('div', { class: 'card-b flush table-wrap' }, h('table', { class: 'table' },
            h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', { class: 'num' }, 'Holes'), h('th', { class: 'num' }, 'Diff.'), h('th', { class: 'num' }, 'Index after'))),
            h('tbody', {}, [...counted].reverse().map((r) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/rounds/${r.id}`; } },
              h('td', {}, fmtDateTime(r.started_at)), h('td', { class: 'num' }, `${r.thru}/${r.holes_total}`),
              h('td', { class: 'num' }, r.differential == null ? '–' : r.differential.toFixed(1)), h('td', { class: 'num' }, fmtIndex(afterByRound.get(r.id))))))))
          : h('div', { class: 'card-b' }, emptyState('trend', 'No counted rounds yet', 'Finish a round of 9 or more holes and it appears here.')))),
      h('div', { class: 'stack-col' },
        card('How it works', 'SimCore Index v1', h('div', { class: 'explain' },
          h('ol', {},
            h('li', {}, h('b', {}, 'Each round gets a differential. '), 'Your strokes minus par, scaled to 18 holes so 9- and 18-hole rounds are comparable. A blow-up hole is capped at net double bogey.'),
            h('li', {}, h('b', {}, 'Your index is your best rounds. '), 'The average of your lowest differentials from your last 20 rounds – the same idea as the World Handicap System.'),
            h('li', {}, h('b', {}, 'New players get a head start. '), 'Until you have 3 rounds, your outdoor index is blended in so one wild round can’t swing it.'),
            h('li', {}, h('b', {}, 'Net scores use it. '), 'In a net league you receive strokes based on your index at the start of the round.')),
          h('p', {}, 'This is a simulator handicap for your venue’s leagues. It is not an official handicap, and your outdoor handicap ID and index are self-reported – they aren’t verified yet.'))))));
  state.cleanup = null;
}

// =================================================================== profile

async function renderProfile() {
  els.view.replaceChildren(card(null, null, loading(4)));
  const { user } = await loadHome();
  if (state.page !== 'profile') return;
  updateChrome();
  const val = (v) => (v == null ? '' : String(v));
  const name = h('input', { class: 'input', name: 'display_name', value: val(user.display_name), maxlength: 60, required: '' });
  const outdoor = h('input', { class: 'input', name: 'outdoor_index', value: val(user.outdoor_index), inputmode: 'decimal', placeholder: 'e.g. 14.2' });
  const ghin = h('input', { class: 'input', name: 'ghin_number', value: val(user.ghin_number), placeholder: 'optional', maxlength: 20 });
  const gspro = h('input', { class: 'input', name: 'gspro_name', value: val(user.gspro_name), maxlength: 60 });
  const ok = h('div', { class: 'form-ok', hidden: true, role: 'status' }, 'Saved.');
  const error = h('div', { class: 'form-error', hidden: true, role: 'alert' });
  const profileForm = h('form', { class: 'form-card', onsubmit: async (event) => {
    event.preventDefault(); ok.hidden = true; error.hidden = true;
    try {
      const res = await patch('/api/me', { display_name: name.value, outdoor_index: outdoor.value, ghin_number: ghin.value, gspro_name: gspro.value });
      state.me = res.user; updateChrome(); ok.hidden = false;
    } catch (err) { error.textContent = err.message; error.hidden = false; }
  } },
  field('Name', name),
  h('div', { class: 'two' }, field('Outdoor handicap ID', ghin), field('Outdoor handicap index', outdoor)),
  h('p', { class: 'note' }, 'Handicap ID and index are on your honour for now – they aren’t checked against any outdoor handicap service.'),
  field('Your name in GSPro', gspro, 'Lets screen-captured rounds be matched to you.'),
  error, ok, h('button', { class: 'btn primary', type: 'submit' }, 'Save changes'));

  const current = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: '' });
  const next = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', minlength: 8, required: '' });
  const pwOk = h('div', { class: 'form-ok', hidden: true, role: 'status' }, 'Password changed.');
  const pwError = h('div', { class: 'form-error', hidden: true, role: 'alert' });
  const pwForm = h('form', { class: 'form-card', onsubmit: async (event) => {
    event.preventDefault(); pwOk.hidden = true; pwError.hidden = true;
    try { await post('/api/me/password', { current_password: current.value, new_password: next.value }); current.value = ''; next.value = ''; pwOk.hidden = false; }
    catch (err) { pwError.textContent = err.message; pwError.hidden = false; }
  } },
  field('Current password', current), field('New password', next, 'At least 8 characters.'), pwError, pwOk,
  h('button', { class: 'btn', type: 'submit' }, 'Change password'));

  els.view.replaceChildren(
    card('Your details', user.email, profileForm),
    card('Password', 'Forgot it? The front desk can issue a temporary one.', pwForm),
    h('div', {}, h('button', { class: 'btn danger', onclick: logout }, icon('logout'), 'Log out')));
  state.cleanup = null;
}

// =================================================================== routing

async function route() {
  if (state.cleanup) { state.cleanup(); state.cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const id = TITLES[parts[0]] ? parts[0] : 'home';
  state.page = id;
  setCurrent(id);
  els.app.classList.remove('nav-open');
  els.view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
  try {
    if (id === 'home') await renderHome();
    else if (id === 'play') await renderPlay(parts[1]);
    else if (id === 'rounds') await (parts[1] ? renderRoundDetail(parts[1]) : renderRounds());
    else if (id === 'leagues') await (parts[1] ? renderLeague(parts[1]) : renderLeagues());
    else if (id === 'handicap') await renderHandicap();
    else await renderProfile();
  } catch (err) {
    if (err.status === 401) { goToLogin(); return; }
    if (state.page === id) els.view.replaceChildren(card(null, null, emptyState('alert', 'Something went wrong', `${err.message}. Is the server still running?`)));
  }
}

// ====================================================================== start

(async function start() {
  let s;
  try { s = await session(); } catch { document.getElementById('root').textContent = 'Can’t reach the server.'; return; }
  if (!s.user) { goToLogin(); return; }
  state.me = s.user;
  state.demo = Boolean(s.demo);
  buildShell();
  try { await loadHome(); } catch (err) { if (err.status === 401) { goToLogin(); return; } }
  updateChrome();
  window.addEventListener('hashchange', route);
  route();
})();
