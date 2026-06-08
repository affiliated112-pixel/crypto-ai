'use strict';
/* ══════════════════════════════════════════════════════
   Romania Crypto Signals — account sync layer
   Persists paper-trading, portfolio and alerts to the user's
   account (server-side) when logged in, with localStorage as
   the offline fallback. Falls back silently for guests.
   ══════════════════════════════════════════════════════ */

const Sync = (() => {
  let _authed = false;
  let _checked = false;
  const _listeners = [];
  let _saveTimer = null;

  /** Has the current visitor an authenticated session? */
  async function checkAuth() {
    try {
      const r = await fetch('/api/me', { cache: 'no-store' });
      const d = await r.json();
      _authed = !!d.authenticated;
    } catch (_) { _authed = false; }
    _checked = true;
    return _authed;
  }

  function isAuthed() { return _authed; }

  /**
   * Pull the saved blob from the account. Returns
   * { paper, portfolio, alerts } or null when guest/unavailable.
   */
  async function pull() {
    if (!_authed) return null;
    try {
      const r = await fetch('/api/userdata', { cache: 'no-store' });
      if (!r.ok) return null;
      const d = await r.json();
      return d.ok ? (d.data || null) : null;
    } catch (_) { return null; }
  }

  /**
   * Push one or more sections to the account (debounced).
   * @param {{paper?:object, portfolio?:object, alerts?:object}} sections
   */
  function push(sections) {
    if (!_authed) return;
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(async () => {
      try {
        await fetch('/api/userdata', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(sections),
        });
      } catch (_) { /* offline — localStorage already has it */ }
    }, 600);
  }

  /** Register a callback fired once the auth state is known. */
  function onReady(cb) {
    if (_checked) cb(_authed);
    else _listeners.push(cb);
  }

  // Resolve auth state once on load and notify listeners.
  checkAuth().then((a) => { _listeners.forEach((cb) => cb(a)); _listeners.length = 0; });

  return { checkAuth, isAuthed, pull, push, onReady };
})();

if (typeof window !== 'undefined') window.Sync = Sync;
