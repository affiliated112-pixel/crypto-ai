'use strict';
/* ══════════════════════════════════════════════════════
   Romania Crypto Signals — Browser Push Notifications
   ══════════════════════════════════════════════════════
   Folosește Service Worker API + Notification API.
   Nu are nevoie de server VAPID — trimite notificări locale
   prin SW message broadcast (orice tab deschis poate declanșa).
*/

const RCB_NOTIF = (() => {
  let _sw = null;
  let _permitted = false;

  // ── Init ──────────────────────────────────────────────────────────────────
  async function init() {
    if (!('serviceWorker' in navigator) || !('Notification' in window)) return;
    try {
      _sw = await navigator.serviceWorker.ready;
      const stored = localStorage.getItem('rcb_notif');
      if (stored === 'granted') {
        _permitted = true;
        _renderBtn('on');
      } else if (stored === 'denied') {
        _renderBtn('denied');
      } else {
        _renderBtn('off');
      }
    } catch (e) {
      console.warn('[push] SW not ready', e);
    }
  }

  // ── Solicită permisiunea ──────────────────────────────────────────────────
  async function requestPermission() {
    if (!('Notification' in window)) {
      _toast('❌', 'Browser-ul tău nu suportă notificări.');
      return;
    }
    const result = await Notification.requestPermission();
    if (result === 'granted') {
      _permitted = true;
      localStorage.setItem('rcb_notif', 'granted');
      _renderBtn('on');
      _toast('🔔', 'Notificări activate! Vei primi alerte pentru semnale noi.');
      // Trimite o notificare de test imediat
      setTimeout(() => sendLocal('✅ Notificări active!', 'Vei fi notificat la fiecare semnal nou de la bot. 🚀'), 1200);
    } else {
      localStorage.setItem('rcb_notif', result);
      _renderBtn('denied');
      _toast('🔕', 'Notificările au fost blocate. Activează-le din setările browser-ului.');
    }
  }

  // ── Toggle on/off ─────────────────────────────────────────────────────────
  function toggle() {
    if (!_permitted) {
      requestPermission();
    } else {
      _permitted = false;
      localStorage.setItem('rcb_notif', 'off');
      _renderBtn('off');
      _toast('🔕', 'Notificări dezactivate.');
    }
  }

  // ── Trimite notificare locală prin SW ─────────────────────────────────────
  function sendLocal(title, body, url) {
    if (!_permitted || !_sw) return;
    if (Notification.permission !== 'granted') return;
    try {
      _sw.active.postMessage({ type: 'SIGNAL_ALERT', title, body, url: url || '/' });
    } catch (e) {
      // Fallback direct (când SW nu e gata)
      new Notification(title, { body, icon: '/assets/rcb-logo.png' });
    }
  }

  // ── Render buton în navbar ─────────────────────────────────────────────────
  function _renderBtn(state) {
    const btn = document.getElementById('notifBtn');
    if (!btn) return;
    if (state === 'on') {
      btn.innerHTML = '🔔';
      btn.title = 'Notificări active — click pentru dezactivare';
      btn.classList.add('notif-on');
      btn.classList.remove('notif-denied');
    } else if (state === 'denied') {
      btn.innerHTML = '🚫';
      btn.title = 'Notificări blocate — activează din setările browser-ului';
      btn.classList.add('notif-denied');
      btn.classList.remove('notif-on');
    } else {
      btn.innerHTML = '🔕';
      btn.title = 'Activează notificările pentru semnale noi';
      btn.classList.remove('notif-on', 'notif-denied');
    }
  }

  function _toast(icon, msg) {
    if (typeof toast === 'function') {
      toast(icon, 'Notificări', msg, icon === '🔔' ? 'toast-buy' : 'toast-sell');
    }
  }

  return { init, toggle, sendLocal, get permitted() { return _permitted; } };
})();

// ── Auto-init când DOM e gata ─────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => RCB_NOTIF.init());
} else {
  RCB_NOTIF.init();
}
