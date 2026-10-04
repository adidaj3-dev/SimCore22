// Talking to the SimCore22 server.

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

// Sent on every state-changing request; the server refuses writes without it (cross-site forgery guard).
const WRITE_HEADERS = { 'Content-Type': 'application/json', 'X-Requested-With': 'SimCore22' };

async function readError(response) {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') detail = body.detail;
    else if (Array.isArray(body.detail)) detail = 'Please check what you entered and try again.';  // validation errors from the framework
  } catch { /* not JSON: keep the status line */ }
  return new ApiError(response.status, detail);
}

export async function get(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  }
  const response = await fetch(url);
  if (!response.ok) throw await readError(response);
  return response.json();
}

async function send(method, path, body) {
  const response = await fetch(path, { method, headers: WRITE_HEADERS, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw await readError(response);
  return response.json();
}

export const post = (path, body = {}) => send('POST', path, body);
export const put = (path, body = {}) => send('PUT', path, body);
export const patch = (path, body = {}) => send('PATCH', path, body);
export const del = (path) => send('DELETE', path);

/** Who is logged in (and whether this venue still needs its first admin). */
export const session = () => get('/api/session');

/** Send someone who isn't logged in to the log-in page, then back here afterwards. */
export function goToLogin() {
  const next = encodeURIComponent(location.pathname + location.hash);
  location.replace(`/login?next=${next}`);
}

export async function logout() {
  try { await post('/api/auth/logout'); } finally { location.assign('/login'); }
}

/**
 * Live updates. Uses server-sent events (the server pushes the leaderboard + engine status the
 * moment they change). If the stream can't connect it falls back to polling every 2s, so a
 * proxy or an old browser degrades to "slightly slower", never to "blank".
 *
 * onUpdate({leaderboard, engine, rounds_signature}); onState('live' | 'polling' | 'offline').
 * Pass { league } to follow one league's hand-entered board instead of the screen-capture board.
 * Returns a function that stops everything.
 */
export function subscribe(onUpdate, onState = () => {}, { league = null } = {}) {
  let source = null;
  let pollTimer = null;
  let failures = 0;
  let stopped = false;

  const poll = async () => {
    try {
      const [leaderboard, engine] = await Promise.all([
        get(league ? `/api/leagues/${league}/board` : '/api/leaderboard'), get('/api/engine')]);
      onUpdate({ leaderboard, engine, rounds_signature: null });
      onState('polling');
    } catch {
      onState('offline');
    }
  };

  const startPolling = () => {
    if (pollTimer || stopped) return;
    poll();
    pollTimer = setInterval(poll, 2000);
  };

  const connect = () => {
    if (stopped || !('EventSource' in window)) return startPolling();
    source = new EventSource(league ? `/api/stream?league=${encodeURIComponent(league)}` : '/api/stream');
    source.addEventListener('update', (event) => {
      failures = 0;
      onUpdate(JSON.parse(event.data));
      onState('live');
    });
    source.onerror = () => {
      failures += 1;
      onState('offline');
      if (failures >= 3) {  // not coming back: poll instead
        source.close();
        startPolling();
      }
    };
  };

  connect();
  return () => {
    stopped = true;
    if (source) source.close();
    if (pollTimer) clearInterval(pollTimer);
  };
}
