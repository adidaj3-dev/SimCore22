// Admin pages for the account side of SimCore22: leagues, players, hand-entered rounds and the
// screen-capture accuracy check. admin.js owns the shell (nav, drawer, routing) and hands it in as `ctx`.

import { h, ICONS, toPar, parClass, fmtDateTime, timeAgo, plural } from './dom.js';
import { get, post, put, patch, del, subscribe } from './api.js';
import { lineChart, sparkline } from './charts.js';
import { scorecard } from './scorecard.js';
import {
  icon, parChip, statusBadge, card, emptyState, loading, toast, person, fmtIndex, manualHoles, field, confirmAction,
} from './ui.js';

const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)}%`);
const unitOf = (league) => (league.ranking === 'net' ? 'Net' : 'Gross');

async function copyText(text, done = 'Copied') {
  try { await navigator.clipboard.writeText(text); toast(done); } catch { toast('Copy failed – select the text instead'); }
}

function joinCodeBox(code) {
  return h('div', { class: 'code-box' },
    h('div', {}, h('div', { class: 'label' }, 'Join code'), h('div', { class: 'code' }, code)),
    h('button', { class: 'btn', onclick: () => copyText(code, 'Join code copied') }, icon('copy'), 'Copy'));
}

function errorLine() { return h('div', { class: 'form-error', role: 'alert', hidden: true }); }
function fail(box, err) { box.textContent = err.message; box.hidden = false; }

export function makePages(ctx) {
  const { els, state } = ctx;
  const here = (id) => state.page === id;

  // ================================================================== leagues

  function leagueForm({ league = null, onDone }) {
    const error = errorLine();
    const name = h('input', { class: 'input', value: league?.name || '', maxlength: 80, required: '', placeholder: 'e.g. Tuesday Night League' });
    const season = h('input', { class: 'input', value: league?.season || '', maxlength: 40, placeholder: 'e.g. Fall 2026' });
    const course = h('input', { class: 'input', value: league?.course_name || '', maxlength: 80, placeholder: 'optional' });
    const holes = h('select', { class: 'select', disabled: league ? '' : null }, [9, 18].map((n) => h('option', { value: n, selected: league?.holes === n ? '' : null }, `${n} holes`)));
    const ranking = h('select', { class: 'select' },
      h('option', { value: 'net', selected: league?.ranking !== 'gross' ? '' : null }, 'Net (with handicaps)'),
      h('option', { value: 'gross', selected: league?.ranking === 'gross' ? '' : null }, 'Gross (no handicaps)'));
    const pars = h('input', { class: 'input', value: league ? league.pars.join(', ') : '', placeholder: 'default: 4, 4, 3, 5, 4, 4, 3, 4, 5' });
    const parsOf = () => {
      const list = pars.value.split(/[,\s]+/).filter(Boolean).map(Number);
      return list.length ? list : null;
    };
    const form = h('form', { class: 'form', onsubmit: async (event) => {
      event.preventDefault();
      error.hidden = true;
      try {
        const body = { name: name.value, season: season.value, course_name: course.value, ranking: ranking.value, pars: parsOf() };
        const saved = league ? await patch(`/api/leagues/${league.id}`, body) : await post('/api/leagues', { ...body, holes: Number(holes.value) });
        toast(league ? 'League updated' : 'League created');
        onDone(saved);
      } catch (err) { fail(error, err); }
    } },
    field('League name', name),
    h('div', { class: 'two' }, field('Season', season), field('Course', course)),
    h('div', { class: 'two' }, field('Length', holes, league ? 'Fixed once a league is created.' : null), field('Ranked by', ranking)),
    field('Par for each hole', pars, 'Comma separated, one per hole. Players see these when entering scores.'),
    error, h('button', { class: 'btn primary big', type: 'submit' }, league ? 'Save changes' : 'Create league'));
    return form;
  }

  async function renderLeagues() {
    els.view.replaceChildren(card(null, null, loading(4)));
    const { leagues } = await get('/api/leagues');
    if (!here('leagues')) return;
    const newButton = h('button', { class: 'btn primary', onclick: () => {
      ctx.openDrawer({ title: 'New league', subtitle: 'Players join with a code you give them' });
      ctx.drawerBody().replaceChildren(leagueForm({ onDone: (l) => { ctx.closeDrawer(false); location.hash = `#/leagues/${l.id}`; } }));
    } }, icon('plus'), 'New league');

    if (!leagues.length) {
      els.view.replaceChildren(card(null, null, emptyState('leagues', 'Create your first league',
        'A league has a course, a length and a way of ranking. Players join with a code, enter their rounds hole by hole, and the standings build themselves.', newButton)));
      state.view = {};
      return;
    }
    els.view.replaceChildren(
      h('div', { style: { display: 'flex', justifyContent: 'flex-end' } }, newButton),
      h('div', { class: 'player-grid-wrap' }, h('div', { class: 'player-grid', style: { padding: 0 } }, leagues.map((l) => h('div', { class: 'player-card league-card' },
        h('div', { class: 'head' }, h('div', { class: 'nm' }, l.name), l.archived ? h('span', { class: 'badge muted hc' }, 'Ended') : null),
        h('div', { class: 'when' }, [l.season, l.course_name, `${l.holes} holes`, `${unitOf(l)} scoring`].filter(Boolean).join(' · ')),
        h('div', { class: 'nums', style: { gridTemplateColumns: '1fr 1.4fr' } },
          h('div', {}, h('div', { class: 'label' }, 'Players'), h('div', { class: 'value' }, l.members)),
          h('div', {}, h('div', { class: 'label' }, 'Join code'), h('div', { class: 'value code-inline' }, l.join_code))),
        h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
          h('a', { class: 'btn primary', href: `#/leagues/${l.id}` }, 'Open'),
          h('a', { class: 'btn', href: `/live?league=${l.id}`, target: '_blank', rel: 'noopener' }, 'Live board', icon('external')),
          h('button', { class: 'btn ghost', onclick: () => copyText(l.join_code, 'Join code copied') }, icon('copy'), 'Code')))))));
    state.view = {};
  }

  async function renderLeague(id) {
    if (state.view?.cleanup) { state.view.cleanup(); state.view = null; }
    els.view.replaceChildren(card(null, null, loading(6)));
    let table, rounds, members, league;
    try {
      [table, { rounds }, { members }] = await Promise.all([
        get(`/api/leagues/${id}/table`), get(`/api/leagues/${id}/rounds`), get(`/api/leagues/${id}/members`)]);
      league = (await get('/api/leagues')).leagues.find((l) => String(l.id) === String(id));
      if (!league) throw new Error('League not found');
    } catch (err) {
      els.view.replaceChildren(card(null, null, emptyState('alert', 'Can’t open that league', err.message, h('a', { class: 'btn', href: '#/leagues' }, 'All leagues'))));
      return;
    }
    if (!here('leagues')) return;
    const unit = unitOf(league);
    const refresh = () => renderLeague(id);

    const boardHost = h('div', {});
    const drawBoard = (board) => {
      const rows = board?.players || [];
      boardHost.replaceChildren(card('Tonight, live', rows.length ? `${unit} to par` : 'Nobody is on the course',
        rows.length ? h('div', { class: 'live-list' }, rows.slice(0, 8).map((p) => h('div', { class: 'live-item' },
          h('div', { class: `rk ${p.rank === 1 ? 'first' : ''}` }, p.tied ? `T${p.rank}` : p.rank),
          person(p.name, [p.bay, p.thru >= board.holes_total ? 'Finished' : `Thru ${p.thru}`].filter(Boolean).join(' · ')),
          parChip(p.vs_par))))
          : h('div', { class: 'card-b' }, h('p', { class: 'muted' }, 'Scores appear as players enter their first hole.')),
        h('a', { class: 'btn ghost', href: `/live?league=${league.id}`, target: '_blank', rel: 'noopener' }, 'Open board', icon('external'))));
    };
    drawBoard(null);

    const addSelect = h('select', { class: 'select', 'aria-label': 'Add a player' }, h('option', { value: '' }, 'Add a player…'));
    get('/api/admin/players').then(({ players }) => {
      const inLeague = new Set(members.map((m) => m.id));
      players.filter((p) => !inLeague.has(p.id) && !p.disabled && p.role === 'player').forEach((p) => addSelect.append(h('option', { value: p.id }, p.display_name)));
    });
    addSelect.addEventListener('change', async () => {
      if (!addSelect.value) return;
      try { await post(`/api/leagues/${id}/members`, { user_id: Number(addSelect.value) }); toast('Player added'); refresh(); } catch (err) { toast(err.message); }
    });

    const membersList = members.length
      ? h('div', { class: 'live-list' }, members.map((m) => {
        const team = h('input', { class: 'input slim', value: m.team || '', placeholder: 'Team', maxlength: 40, 'aria-label': `Team for ${m.display_name}` });
        team.addEventListener('change', async () => { try { await put(`/api/leagues/${id}/members/${m.id}/team`, { team: team.value }); toast('Team saved'); } catch (err) { toast(err.message); } });
        return h('div', { class: 'live-item', style: { gridTemplateColumns: 'minmax(0,1fr) 120px auto' } },
          h('a', { href: `#/players/${m.id}`, class: 'plain' }, person(m.display_name, `Index ${fmtIndex(m.indoor_index)}`)),
          team,
          h('button', { class: 'btn icon ghost', 'aria-label': `Remove ${m.display_name}`, html: ICONS.close, onclick: async () => {
            if (!confirmAction(`Remove ${m.display_name} from ${league.name}? Their rounds stay on record.`)) return;
            try { await del(`/api/leagues/${id}/members/${m.id}`); refresh(); } catch (err) { toast(err.message); }
          } }));
      }))
      : h('div', { class: 'card-b' }, h('p', { class: 'muted' }, 'No players yet. Share the join code, or add people below.'));

    els.view.replaceChildren(
      h('div', { class: 'hello' },
        h('div', {}, h('h2', {}, league.name), h('p', {}, [league.season, league.course_name, `${league.holes} holes`, `${unit} scoring`].filter(Boolean).join(' · '))),
        h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
          h('a', { class: 'btn', href: '#/leagues' }, 'All leagues'),
          h('button', { class: 'btn', onclick: () => {
            ctx.openDrawer({ title: 'League settings', subtitle: league.name });
            ctx.drawerBody().replaceChildren(
              leagueForm({ league, onDone: () => { ctx.closeDrawer(false); refresh(); } }),
              h('div', {}, h('button', { class: 'btn danger', onclick: async () => {
                const ending = !league.archived;
                if (!confirmAction(ending ? `End ${league.name}? Players can no longer start rounds in it; everything stays on record.` : `Reopen ${league.name}?`)) return;
                try { await patch(`/api/leagues/${id}`, { archived: ending }); ctx.closeDrawer(false); refresh(); } catch (err) { toast(err.message); }
              } }, league.archived ? 'Reopen league' : 'End league')));
          } }, icon('edit'), 'Settings'),
          h('a', { class: 'btn primary', href: `/live?league=${league.id}`, target: '_blank', rel: 'noopener' }, icon('live'), 'Live board'))),
      joinCodeBox(league.join_code),
      h('div', { class: 'grid-2' },
        h('div', { class: 'stack-col' },
          card('Standings', `Average ${unit.toLowerCase()} score to par · finished rounds`, h('div', { class: 'card-b flush table-wrap' }, standingsTable(table.players))),
          card('Rounds', 'Every round entered in this league · click to view or correct',
            rounds.length ? h('div', { class: 'card-b flush table-wrap' }, leagueRoundsTable(rounds)) : h('div', { class: 'card-b' }, emptyState('rounds', 'No rounds yet', 'They appear here as players enter scores.')))),
        h('div', { class: 'stack-col' },
          boardHost,
          card('Players', `${plural(members.length, 'member')}`, membersList, addSelect))));
    state.view = { refresh, cleanup: subscribe(({ leaderboard }) => drawBoard(leaderboard), () => {}, { league: league.id }) };
  }

  function standingsTable(players) {
    if (!players.length) return emptyState('players', 'No players yet', 'Players appear here when they join.');
    return h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Player'), h('th', { class: 'hide-sm' }, 'Team'), h('th', { class: 'num' }, 'Rds'), h('th', { class: 'num' }, 'Avg'),
        h('th', { class: 'num hide-sm' }, 'Best'), h('th', { class: 'num hide-sm' }, 'Index'), h('th', { class: 'hide-sm', style: { width: '90px' } }, 'Form'))),
      h('tbody', {}, players.map((p) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/players/${p.user_id}`; } },
        h('td', {}, p.rounds ? (p.tied ? `T${p.rank}` : p.rank) : '–'),
        h('td', {}, person(p.name)),
        h('td', { class: 'muted hide-sm' }, p.team || '–'),
        h('td', { class: 'num' }, p.rounds),
        h('td', { class: 'num' }, p.avg_vs_par == null ? '–' : parChip(Math.round(p.avg_vs_par * 10) / 10)),
        h('td', { class: 'num hide-sm' }, p.best_vs_par == null ? '–' : toPar(p.best_vs_par)),
        h('td', { class: 'num hide-sm' }, fmtIndex(p.index)),
        h('td', { class: 'hide-sm' }, sparkline(p.trend))))));
  }

  function leagueRoundsTable(rounds) {
    return h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', {}, 'When'), h('th', { class: 'hide-sm' }, 'Bay'), h('th', { class: 'num' }, 'Thru'),
        h('th', { class: 'num' }, 'Gross'), h('th', { class: 'num' }, 'To par'), h('th', {}, 'Status'))),
      h('tbody', {}, rounds.slice(0, 40).map((r) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/round/${r.id}`; } },
        h('td', {}, person(r.player)),
        h('td', { class: 'muted nowrap' }, fmtDateTime(r.started_at)),
        h('td', { class: 'muted hide-sm' }, r.bay || '–'),
        h('td', { class: 'num' }, `${r.thru}/${r.holes_total}`),
        h('td', { class: 'num' }, r.gross ?? '–'),
        h('td', { class: 'num' }, parChip(r.vs_par)),
        h('td', {}, statusBadge(r.status))))));
  }

  // ============================================================ a hand-entered round

  async function showRound(id) {
    ctx.openDrawer({ title: 'Round', subtitle: 'Loading…' });
    let r;
    try { r = await get(`/api/play/rounds/${id}`); } catch (err) {
      ctx.drawerBody().replaceChildren(emptyState('alert', 'Round not found', err.message));
      return;
    }
    const net = r.course_handicap > 0;
    ctx.openDrawer({ title: r.player || 'Round', subtitle: `${r.course_name || 'Casual round'} · ${fmtDateTime(r.started_at)}`, avatarName: r.player });
    const sc = scorecard(manualHoles(r));

    const inputs = r.holes.map((x) => {
      const input = h('input', { class: 'input slim num', type: 'number', min: 1, max: 15, value: x.strokes ?? '', placeholder: '–', 'aria-label': `Hole ${x.hole} strokes` });
      input.addEventListener('change', async () => {
        if (input.value === '') return;
        try { await put(`/api/play/rounds/${r.id}/holes/${x.hole}`, { strokes: Number(input.value) }); toast('Saved – handicap updated'); showRound(id); }
        catch (err) { toast(err.message); input.value = x.strokes ?? ''; }
      });
      return h('div', { class: 'edit-hole' }, h('small', {}, `${x.hole}`), h('span', { class: 'faint' }, `Par ${x.par}`), input);
    });

    ctx.drawerBody().replaceChildren(
      h('div', { class: 'stat-band', style: { gridTemplateColumns: net ? '1.3fr 1fr 1fr 1fr' : '1.3fr 1fr 1fr' } },
        h('div', {}, h('div', { class: 'label' }, 'To par'), h('div', { class: `value ${parClass(r.vs_par)}` }, toPar(r.vs_par))),
        h('div', {}, h('div', { class: 'label' }, 'Gross'), h('div', { class: 'value' }, r.gross ?? '–')),
        h('div', {}, h('div', { class: 'label' }, 'Holes'), h('div', { class: 'value' }, `${r.thru}/${r.holes_total}`)),
        net ? h('div', {}, h('div', { class: 'label' }, 'Net'), h('div', { class: 'value' }, r.net ?? '–')) : null),
      h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, statusBadge(r.status),
        r.bay ? h('span', { class: 'badge muted' }, r.bay) : null,
        r.counts ? h('span', { class: 'badge ok' }, 'Counts toward handicap') : h('span', { class: 'badge muted' }, 'Not counted for handicap'),
        r.differential != null ? h('span', { class: 'badge' }, `Differential ${r.differential.toFixed(1)}`) : null),
      h('div', {}, h('div', { class: 'section-title' }, 'Scorecard'), sc.element),
      h('div', {}, h('div', { class: 'section-title' }, 'Correct a score'),
        h('div', { class: 'edit-holes' }, inputs),
        h('p', { class: 'faint', style: { marginTop: '8px', fontSize: '12.5px' } }, 'Changing a hole recalculates this player’s handicap and every table straight away. Each correction is logged.')),
      h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        h('a', { class: 'btn', href: `/app#/play/${r.id}`, target: '_blank', rel: 'noopener' }, 'Open in entry screen', icon('external')),
        h('button', { class: 'btn danger', onclick: async () => {
          if (!confirmAction('Delete this round? It disappears from every table and the player’s handicap is recalculated. This can’t be undone.')) return;
          try { await del(`/api/play/rounds/${r.id}`); toast('Round deleted'); ctx.closeDrawer(true); if (state.view?.refresh) state.view.refresh(); else ctx.route(true); } catch (err) { toast(err.message); }
        } }, 'Delete round')));
  }

  // =================================================================== players

  async function renderPlayers() {
    els.view.replaceChildren(card(null, null, loading(6)));
    const { players } = await get('/api/admin/players');
    if (!here('players')) return;
    const host = h('div', { class: 'card-b flush table-wrap' });
    const count = h('span', { class: 'faint', style: { fontSize: '13px' } });
    const draw = (q = '') => {
      const rows = players.filter((p) => `${p.display_name} ${p.email} ${p.gspro_name || ''}`.toLowerCase().includes(q.toLowerCase()));
      count.textContent = plural(rows.length, 'player');
      host.replaceChildren(rows.length ? h('table', { class: 'table' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', { class: 'num' }, 'Indoor'), h('th', { class: 'num hide-sm' }, 'Outdoor'), h('th', { class: 'hide-sm' }, 'Outdoor ID'),
          h('th', { class: 'hide-sm' }, 'Leagues'), h('th', { class: 'num' }, 'Rounds'), h('th', { class: 'hide-sm' }, 'Last played'))),
        h('tbody', {}, rows.map((p) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/players/${p.id}`; } },
          h('td', {}, person(p.display_name, p.email), p.role === 'admin' ? h('span', { class: 'badge info', style: { marginLeft: '8px' } }, 'Admin') : null,
            p.disabled ? h('span', { class: 'badge danger', style: { marginLeft: '8px' } }, 'Disabled') : null),
          h('td', { class: 'num' }, fmtIndex(p.indoor_index)),
          h('td', { class: 'num hide-sm muted' }, fmtIndex(p.outdoor_index)),
          h('td', { class: 'muted hide-sm' }, p.ghin_number || '–'),
          h('td', { class: 'muted hide-sm' }, p.leagues.join(', ') || '–'),
          h('td', { class: 'num' }, p.rounds),
          h('td', { class: 'muted hide-sm' }, p.last_played ? timeAgo(p.last_played) : '–')))))
        : emptyState('players', players.length ? 'No players match' : 'No players yet', players.length ? 'Try a different name.' : 'Players appear here when they sign up.'));
    };
    els.view.replaceChildren(h('section', { class: 'card' },
      h('div', { class: 'toolbar' }, h('div', { class: 'grow' }, count),
        h('label', { class: 'search' }, h('span', { html: ICONS.search }), h('input', { type: 'search', placeholder: 'Search name, email or GSPro name', 'aria-label': 'Search players', oninput: (e) => draw(e.target.value) }))),
      host));
    state.view = { refresh: renderPlayers };
    draw();
  }

  async function showPlayer(id) {
    ctx.openDrawer({ title: 'Player', subtitle: 'Loading…' });
    let p;
    try { p = await get(`/api/admin/players/${id}`); } catch (err) {
      ctx.drawerBody().replaceChildren(emptyState('alert', 'Player not found', err.message));
      return;
    }
    const u = p.user;
    ctx.openDrawer({ title: u.display_name, subtitle: u.email, avatarName: u.display_name });
    const refresh = () => { showPlayer(id); if (state.view?.refresh) state.view.refresh(); };

    const val = (v) => (v == null ? '' : String(v));
    const name = h('input', { class: 'input', value: val(u.display_name), maxlength: 60 });
    const outdoor = h('input', { class: 'input', value: val(u.outdoor_index), inputmode: 'decimal' });
    const ghin = h('input', { class: 'input', value: val(u.ghin_number), maxlength: 20 });
    const gspro = h('input', { class: 'input', value: val(u.gspro_name), maxlength: 60 });
    const error = errorLine();
    const editForm = h('form', { class: 'form', onsubmit: async (event) => {
      event.preventDefault(); error.hidden = true;
      try { await patch(`/api/admin/players/${id}`, { display_name: name.value, outdoor_index: outdoor.value, ghin_number: ghin.value, gspro_name: gspro.value }); toast('Saved'); refresh(); }
      catch (err) { fail(error, err); }
    } },
    field('Name', name), h('div', { class: 'two' }, field('Outdoor handicap ID', ghin), field('Outdoor index', outdoor)),
    field('Name in GSPro', gspro, 'Matches screen-captured rounds to this player.'),
    error, h('button', { class: 'btn primary', type: 'submit' }, 'Save details'));

    const history = p.handicap.history.filter((x) => x.index != null).map((x) => ({ label: fmtDateTime(x.at), value: x.index }));
    const mini = (label, value) => h('div', {}, h('div', { class: 'label' }, label), h('div', { class: 'value' }, value));
    const tempBox = h('div', { class: 'callout ok', hidden: true });

    const resetPassword = async () => {
      if (!confirmAction(`Give ${u.display_name} a temporary password? They’ll be logged out everywhere and must use the new one.`)) return;
      try {
        const { temporary_password: temp } = await post(`/api/admin/players/${id}/reset-password`);
        tempBox.replaceChildren(icon('check'), h('div', {}, h('b', {}, 'Temporary password: '), h('code', {}, temp), ' ',
          h('button', { class: 'btn', style: { marginLeft: '8px' }, onclick: () => copyText(temp, 'Copied') }, icon('copy'), 'Copy'),
          h('div', { class: 'faint' }, 'Tell them in person. They can change it under Profile.')));
        tempBox.hidden = false;
      } catch (err) { toast(err.message); }
    };

    const leagueSelect = h('select', { class: 'select', 'aria-label': 'League' }, p.leagues.map((l) => h('option', { value: l.id }, l.name)), h('option', { value: '' }, 'Casual round'));
    const enterFor = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, leagueSelect, h('button', { class: 'btn', onclick: async () => {
      try {
        const body = leagueSelect.value ? { user_id: id, league_id: Number(leagueSelect.value) } : { user_id: id, holes: 9 };
        const round = await post('/api/play/rounds', body);
        window.open(`/app#/play/${round.id}`, '_blank', 'noopener');
      } catch (err) { toast(err.message); }
    } }, 'Enter a round for them'));

    ctx.drawerBody().replaceChildren(
      h('div', { class: 'mini-stats' }, mini('Indoor index', fmtIndex(p.handicap.index)), mini('Outdoor index', fmtIndex(p.handicap.outdoor_index)),
        mini('Rounds', p.stats.rounds), mini('Avg to par', p.stats.avg_vs_par == null ? '–' : toPar(Math.round(p.stats.avg_vs_par)))),
      u.disabled ? h('div', { class: 'callout danger' }, icon('alert'), h('div', {}, h('b', {}, 'Account disabled. '), 'They can’t log in.')) : null,
      h('div', {}, h('div', { class: 'section-title' }, 'Indoor handicap · lower is better'),
        h('div', { class: 'card' }, h('div', { class: 'card-b' }, history.length >= 2 ? lineChart(history, { format: (v) => (v === 0 ? '0' : String(v)) })
          : h('p', { class: 'muted' }, 'The chart appears after a couple of rounds.')))),
      h('div', {}, h('div', { class: 'section-title' }, 'Details'), editForm),
      h('div', {}, h('div', { class: 'section-title' }, 'Rounds'),
        p.rounds.length ? h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
          h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', { class: 'num' }, 'Thru'), h('th', { class: 'num' }, 'To par'), h('th', {}, 'Status'))),
          h('tbody', {}, p.rounds.filter((r) => r.thru > 0 || r.status === 'in_progress').slice(0, 25).map((r) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/round/${r.id}`; } },
            h('td', { class: 'muted nowrap' }, fmtDateTime(r.started_at)), h('td', { class: 'num' }, `${r.thru}/${r.holes_total}`),
            h('td', { class: 'num' }, parChip(r.vs_par)), h('td', {}, statusBadge(r.status))))))))
          : h('p', { class: 'muted' }, 'No rounds yet.')),
      h('div', {}, h('div', { class: 'section-title' }, 'Actions'), h('div', { style: { display: 'grid', gap: '10px' } },
        enterFor, tempBox,
        h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
          h('button', { class: 'btn', onclick: resetPassword }, icon('key'), 'Reset password'),
          h('button', { class: 'btn', onclick: async () => {
            const to = u.role === 'admin' ? 'player' : 'admin';
            if (!confirmAction(to === 'admin' ? `Make ${u.display_name} a venue admin? They’ll be able to see and change everything.` : `Remove admin access from ${u.display_name}?`)) return;
            try { await post(`/api/admin/players/${id}/role`, { role: to }); toast('Role updated'); refresh(); } catch (err) { toast(err.message); }
          } }, u.role === 'admin' ? 'Remove admin' : 'Make admin'),
          h('button', { class: 'btn danger', onclick: async () => {
            if (!confirmAction(u.disabled ? `Re-enable ${u.display_name}?` : `Disable ${u.display_name}? They’ll be logged out and can’t log in. Their rounds stay on record.`)) return;
            try { await post(`/api/admin/players/${id}/disabled`, { disabled: !u.disabled }); toast(u.disabled ? 'Account enabled' : 'Account disabled'); refresh(); } catch (err) { toast(err.message); }
          } }, u.disabled ? 'Enable account' : 'Disable account')))));
  }

  // ==================================================== capture accuracy (vs hand entry)

  async function renderCapture() {
    const f = { days: 30, league: '' };
    const host = h('div', { class: 'stack-col' });
    const daysChips = [[7, '7 days'], [30, '30 days'], [90, '90 days'], [365, 'Year']].map(([d, label]) =>
      h('button', { class: 'chip', 'aria-pressed': d === f.days ? 'true' : 'false', onclick: (e) => {
        f.days = d; daysChips.forEach((c) => c.setAttribute('aria-pressed', c === e.currentTarget ? 'true' : 'false')); load();
      } }, label));
    const leagueSelect = h('select', { class: 'select slim', 'aria-label': 'League', onchange: () => { f.league = leagueSelect.value; load(); } }, h('option', { value: '' }, 'All leagues'));
    get('/api/leagues').then(({ leagues }) => leagues.forEach((l) => leagueSelect.append(h('option', { value: l.id }, l.name))));

    els.view.replaceChildren(
      h('div', { class: 'callout info' }, icon('target'), h('div', {}, h('b', {}, 'How accurate is the screen capture? '),
        'Every round a player enters by hand is compared, hole by hole, with the round the engine read from GSPro for the same player at about the same time. ',
        'Set each player’s “Name in GSPro” so the two can be matched.')),
      h('section', { class: 'card' }, h('div', { class: 'toolbar' }, h('div', { class: 'chips' }, daysChips), h('div', { class: 'grow' }), leagueSelect)),
      host);

    async function load() {
      host.replaceChildren(card(null, null, loading(5)));
      const result = await get('/api/admin/accuracy', { days: f.days, league_id: f.league });
      if (!here('capture')) return;
      const s = result.summary;
      const attention = [];
      if (result.unmatched_manual.length) attention.push(card('Entered by hand, no capture found', `${result.unmatched_manual.length} — is the engine running on that bay, or the GSPro name spelled differently?`,
        h('div', { class: 'live-list' }, result.unmatched_manual.slice(0, 10).map((m) => h('a', { class: 'live-item plain', href: `#/round/${m.manual_round_id}`, style: { gridTemplateColumns: 'minmax(0,1fr) auto' } },
          person(m.player, fmtDateTime(m.started_at)), h('span', { class: 'badge muted' }, m.in_progress ? 'In progress' : `${m.thru} holes`))))));
      if (result.unmatched_capture.length) attention.push(card('Captured, never entered by hand', `${result.unmatched_capture.length} — fine for practice rounds`,
        h('div', { class: 'live-list' }, result.unmatched_capture.slice(0, 10).map((c) => h('div', { class: 'live-item', style: { gridTemplateColumns: 'minmax(0,1fr) auto' } },
          person(c.player, fmtDateTime(c.finished_at)), h('span', { class: `badge ${c.known_player ? 'muted' : 'warn'}` }, c.known_player ? `Gross ${c.gross ?? '–'}` : 'No matching account'))))));

      host.replaceChildren(
        h('div', { class: 'kpis' },
          h('div', { class: 'card kpi' }, h('div', { class: 'label' }, 'Hole accuracy'), h('div', { class: 'value' }, pct(s.hole_accuracy)),
            h('div', { class: 'foot' }, s.holes_compared ? `${s.holes_matching} of ${s.holes_compared} holes match` : 'Nothing to compare yet')),
          h('div', { class: 'card kpi' }, h('div', { class: 'label' }, 'Rounds compared'), h('div', { class: 'value' }, s.pairs), h('div', { class: 'foot' }, `${s.rounds_exact} matched on every hole`)),
          h('div', { class: 'card kpi' }, h('div', { class: 'label' }, 'Verified by scorecard'), h('div', { class: 'value' }, pct(s.verified.accuracy)),
            h('div', { class: 'foot' }, `${plural(s.verified.rounds, 'round')} read from GSPro’s card`)),
          h('div', { class: 'card kpi' }, h('div', { class: 'label' }, 'Counted from shots'), h('div', { class: 'value' }, pct(s.counted_from_shots.accuracy)),
            h('div', { class: 'foot' }, `${plural(s.counted_from_shots.rounds, 'round')} without a scorecard`))),
        result.pairs.length ? card('Round by round', 'Click one to see which holes differ',
          h('div', { class: 'card-b flush table-wrap' }, h('table', { class: 'table' },
            h('thead', {}, h('tr', {}, h('th', {}, 'Player'), h('th', {}, 'When'), h('th', { class: 'hide-sm' }, 'Source'), h('th', { class: 'num' }, 'Holes'),
              h('th', { style: { width: '150px' } }, 'Accuracy'), h('th', { class: 'num hide-sm' }, 'Entered'), h('th', { class: 'num hide-sm' }, 'Captured'))),
            h('tbody', {}, result.pairs.map((p) => h('tr', { class: 'click', tabindex: 0, onclick: () => { location.hash = `#/capture/${p.manual_round_id}`; } },
              h('td', {}, person(p.player)), h('td', { class: 'muted nowrap' }, fmtDateTime(p.started_at)),
              h('td', { class: 'hide-sm' }, p.verified ? h('span', { class: 'badge ok' }, icon('shield'), 'Verified') : h('span', { class: 'badge muted' }, 'Shots')),
              h('td', { class: 'num' }, `${p.holes_matching}/${p.holes_compared}`),
              h('td', {}, h('div', { class: 'acc' }, h('div', { class: 'bar' }, h('i', { style: { width: `${Math.round((p.hole_accuracy || 0) * 100)}%` } })), h('span', { class: 'num' }, pct(p.hole_accuracy)))),
              h('td', { class: 'num hide-sm' }, p.gross_manual ?? '–'),
              h('td', { class: `num hide-sm ${p.gross_matches ? '' : 'over'}` }, p.gross_captured ?? '–')))))))
          : card(null, null, emptyState('target', 'Nothing to compare yet',
            'Once the engine has read a round and a player has entered the same round by hand, the comparison shows up here. Make sure the engine is running (run_bay.bat) and each player’s GSPro name is set.')),
        ...attention);
    }
    state.view = { refresh: load };
    await load();
  }

  async function showComparison(manualId) {
    ctx.openDrawer({ title: 'Capture check', subtitle: 'Loading…' });
    const result = await get('/api/admin/accuracy', { days: 365 });
    const p = result.pairs.find((x) => String(x.manual_round_id) === String(manualId));
    if (!p) { ctx.drawerBody().replaceChildren(emptyState('target', 'No comparison for that round', 'It may be outside the date range, or no captured round matched it.')); return; }
    ctx.openDrawer({ title: p.player, subtitle: `Entered ${fmtDateTime(p.started_at)}`, avatarName: p.player });
    const mismatches = p.holes.filter((x) => x.match === false).length;
    ctx.drawerBody().replaceChildren(
      h('div', { class: `callout ${mismatches ? 'warn' : 'ok'}` }, icon(mismatches ? 'alert' : 'check'),
        h('div', {}, h('b', {}, mismatches ? `${plural(mismatches, 'hole')} differ. ` : 'Every hole matches. '),
          p.verified ? 'The captured scores were read from GSPro’s scorecard.' : 'The captured scores were counted from shots, not read from a scorecard.')),
      h('div', { class: 'mini-stats' },
        h('div', {}, h('div', { class: 'label' }, 'Hole accuracy'), h('div', { class: 'value' }, pct(p.hole_accuracy))),
        h('div', {}, h('div', { class: 'label' }, 'Entered gross'), h('div', { class: 'value' }, p.gross_manual ?? '–')),
        h('div', {}, h('div', { class: 'label' }, 'Captured gross'), h('div', { class: 'value' }, p.gross_captured ?? '–')),
        h('div', {}, h('div', { class: 'label' }, 'Not captured'), h('div', { class: 'value' }, p.holes_missing_from_capture))),
      h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Hole'), h('th', { class: 'num' }, 'Entered'), h('th', { class: 'num' }, 'Captured'), h('th', {}, ''))),
        h('tbody', {}, p.holes.map((x) => h('tr', {},
          h('td', {}, x.hole), h('td', { class: 'num' }, x.manual), h('td', { class: 'num' }, x.captured ?? '–'),
          h('td', {}, x.match === true ? h('span', { class: 'badge ok' }, 'Match') : x.match === false ? h('span', { class: 'badge warn' }, 'Differs') : h('span', { class: 'badge muted' }, 'Not read')))))))),
      h('a', { class: 'btn', href: `#/round/${p.manual_round_id}` }, 'View the entered round'));
  }

  return { renderLeagues, renderLeague, showRound, renderPlayers, showPlayer, renderCapture, showComparison };
}
