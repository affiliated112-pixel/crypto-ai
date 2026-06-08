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
  // Pending sections to flush + one debounce timer shared across calls.
  // We MERGE pending sections so a paper save never cancels an alerts save.
  let _pending = {};
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

  /** Flush all pending sections in a single request. */
  async function _flush() {
    const payload = _pending;
    _pending = {};
    if (!_authed || !Object.keys(payload).length) return;
    try {
      await fetch('/api/userdata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (_) { /* offline — localStorage already has it */ }
  }

  /**
   * Push one or more sections to the account (debounced + merged).
   * @param {{paper?:object, portfolio?:object, alerts?:object}} sections
   */
  function push(sections) {
    if (!_authed || !sections) return;
    Object.assign(_pending, sections); // merge, never overwrite other sections
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(_flush, 600);
  }

  /** Register a callback fired once the auth state is known. */
  function onReady(cb) {
    if (typeof cb !== 'function') return;
    if (_checked) cb(_authed);
    else _listeners.push(cb);
  }

  // Flush any pending writes before the tab closes (best-effort).
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      if (!_authed || !Object.keys(_pending).length) return;
      try {
        const blob = new Blob([JSON.stringify(_pending)], { type: 'application/json' });
        navigator.sendBeacon('/api/userdata', blob);
        _pending = {};
      } catch (_) {}
    });
  }

  // Resolve auth state once on load and notify listeners.
  checkAuth().then((a) => { _listeners.forEach((cb) => cb(a)); _listeners.length = 0; });

  return { checkAuth, isAuthed, pull, push, onReady };
})();

if (typeof window !== 'undefined') window.Sync = Sync;
