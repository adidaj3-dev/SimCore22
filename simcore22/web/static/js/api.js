// Talking to the SimCore22 server.

export async function get(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

/**
 * Live updates. Uses server-sent events (the server pushes the leaderboard + engine status the
 * moment they change). If the stream can't connect it falls back to polling every 2s, so a
 * proxy or an old browser degrades to "slightly slower", never to "blank".
 *
 * onUpdate({leaderboard, engine, rounds_signature}); onState('live' | 'polling' | 'offline').
 * Returns a function that stops everything.
 */
export function subscribe(onUpdate, onState = () => {}) {
  let source = null;
  let pollTimer = null;
  let failures = 0;
  let stopped = false;

  const poll = async () => {
    try {
      const [leaderboard, engine] = await Promise.all([get('/api/leaderboard'), get('/api/engine')]);
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
    source = new EventSource('/api/stream');
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
