// The log-in / sign-up page. Also handles the very first run (create the venue's admin) and,
// in demo mode, one-click log-in as the fictional admin or a fictional player.

import { h, clear, LOGO } from './dom.js';
import { session, post } from './api.js';
import { field, themeButton } from './ui.js';

const root = document.getElementById('root');
const params = new URLSearchParams(location.search);

function destination(user) {
  const next = params.get('next');
  // only ever back into this site: "//host" and "/\host" are both read by browsers as another site
  if (next && /^\/(?![/\\])/.test(next)) return next;
  return user.role === 'admin' ? '/admin' : '/app';
}

function input(props) {
  return h('input', { class: 'input', required: props.required !== false, ...props });
}

function errorBox() { return h('div', { class: 'form-error', role: 'alert', hidden: true }); }
function showError(box, message) { box.textContent = message; box.hidden = false; }

/** Wire a form: disable the button while working, show the server's reason on failure. */
function submitter(form, button, box, work) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    box.hidden = true;
    const label = button.textContent;
    button.disabled = true;
    button.textContent = 'One moment…';
    try {
      const { user } = await work(Object.fromEntries(new FormData(form)));
      location.assign(destination(user));
    } catch (err) {
      showError(box, err.message);
      button.disabled = false;
      button.textContent = label;
    }
  });
}

function loginForm() {
  const box = errorBox();
  const button = h('button', { class: 'btn primary wide', type: 'submit' }, 'Log in');
  const form = h('form', { class: 'form', autocomplete: 'on' },
    field('Email', input({ name: 'email', type: 'email', autocomplete: 'username', autofocus: true })),
    field('Password', input({ name: 'password', type: 'password', autocomplete: 'current-password' })),
    box, button);
  submitter(form, button, box, (body) => post('/api/auth/login', body));
  return form;
}

function signupForm() {
  const box = errorBox();
  const button = h('button', { class: 'btn primary wide', type: 'submit' }, 'Create my account');
  const form = h('form', { class: 'form', autocomplete: 'on' },
    field('Your name', input({ name: 'display_name', autocomplete: 'name', maxlength: 60 })),
    field('Email', input({ name: 'email', type: 'email', autocomplete: 'username' })),
    field('Password', input({ name: 'password', type: 'password', autocomplete: 'new-password', minlength: 8 }), 'At least 8 characters.'),
    h('div', { class: 'two' },
      field('Outdoor handicap ID', input({ name: 'ghin_number', placeholder: 'optional', required: false, maxlength: 20 })),
      field('Outdoor handicap index', input({ name: 'outdoor_index', inputmode: 'decimal', placeholder: 'e.g. 14.2', required: false, maxlength: 6 }))),
    h('p', { class: 'note' }, 'These are on your honour for now – SimCore22 doesn’t check them against any outdoor handicap service. Your index gives you a fair starting handicap until you have a few simulator rounds of your own.'),
    field('Your name in GSPro', input({ name: 'gspro_name', required: false, maxlength: 60, placeholder: 'if different from above' }),
      'Lets screen-captured rounds be matched to you.'),
    field('League join code', input({ name: 'join_code', required: false, maxlength: 8, placeholder: 'optional – from your venue', autocapitalize: 'characters' })),
    box, button);
  submitter(form, button, box, (body) => post('/api/auth/signup', body));
  return form;
}

function setupForm() {
  const box = errorBox();
  const button = h('button', { class: 'btn primary wide', type: 'submit' }, 'Create the admin account');
  const form = h('form', { class: 'form', autocomplete: 'on' },
    field('Your name', input({ name: 'display_name', autocomplete: 'name', maxlength: 60 })),
    field('Email', input({ name: 'email', type: 'email', autocomplete: 'username' })),
    field('Password', input({ name: 'password', type: 'password', autocomplete: 'new-password', minlength: 8 }), 'At least 8 characters. You’ll use this to run the venue.'),
    box, button);
  submitter(form, button, box, (body) => post('/api/auth/setup', body));
  return form;
}

function demoPanel(demo) {
  const box = errorBox();
  const go = async (email) => {
    box.hidden = true;
    try { const { user } = await post('/api/auth/login', { email, password: demo.password }); location.assign(destination(user)); }
    catch (err) { showError(box, err.message); }
  };
  return h('div', { class: 'demo-panel' },
    h('div', { class: 'demo-head' }, h('span', { class: 'badge demo-flag' }, 'Demo'), h('b', {}, 'Try it without signing up')),
    h('p', {}, 'Fictional venue, fictional players. Log in as:'),
    h('div', { class: 'demo-buttons' },
      h('button', { class: 'btn', type: 'button', onclick: () => go(demo.admin.email) }, 'Venue manager'),
      demo.players.slice(0, 2).map((p) => h('button', { class: 'btn', type: 'button', onclick: () => go(p.email) }, p.name))),
    box);
}

function tabs(modes, active, onPick) {
  return h('div', { class: 'seg', role: 'tablist' }, modes.map(([id, label]) =>
    h('button', { type: 'button', role: 'tab', 'aria-selected': id === active ? 'true' : 'false', onclick: () => onPick(id) }, label)));
}

function build(state) {
  const panel = h('div', { class: 'auth-body' });
  const draw = (mode) => {
    const forms = { login: loginForm, signup: signupForm, setup: setupForm };
    const titles = {
      login: ['Welcome back', 'Log in to enter your round and see your handicap.'],
      signup: ['Create your account', 'Takes a minute. Then you can enter rounds hole by hole and follow your league live.'],
      setup: ['Set up your venue', 'Create the first admin account. It can run leagues, players and the bay screens.'],
    };
    clear(panel).append(
      mode === 'setup' ? null : tabs([['login', 'Log in'], ['signup', 'Sign up']], mode, draw),
      h('h1', {}, titles[mode][0]),
      h('p', { class: 'lede' }, titles[mode][1]),
      forms[mode](),
      state.demo && mode !== 'setup' ? demoPanel(state.demo) : null);
  };
  draw(state.needs_setup && state.can_setup ? 'setup' : 'login');

  clear(root).append(h('div', { class: 'auth' },
    h('aside', { class: 'auth-side' },
      h('div', { class: 'brand' }, h('span', { html: LOGO }), h('div', {}, 'SimCore22', h('small', {}, 'Indoor golf, scored'))),
      h('div', { class: 'pitch' },
        h('h2', {}, 'Every hole. Every league. Live on every bay.'),
        h('ul', {},
          h('li', {}, 'Enter your round hole by hole – the leaderboard updates the moment you do.'),
          h('li', {}, 'An indoor handicap built from the rounds you really play.'),
          h('li', {}, 'Season standings and stats, without a spreadsheet.')))),
    h('main', { class: 'auth-main' }, h('div', { class: 'auth-top' }, themeButton()), panel)));

  if (state.needs_setup && !state.can_setup) {
    panel.prepend(h('div', { class: 'callout warn', style: { marginBottom: '16px' } },
      h('div', {}, h('b', {}, 'This venue isn’t set up yet. '), 'The admin account has to be created on the venue PC itself.')));
  }
}

session().then((state) => {
  if (state.user) { location.replace(destination(state.user)); return; }
  build(state);
}).catch(() => {
  clear(root).append(h('div', { class: 'auth-main' }, h('div', { class: 'auth-body' },
    h('h1', {}, 'Can’t reach the server'), h('p', { class: 'lede' }, 'Check the venue PC is on and this page’s address is right, then reload.'))));
});
