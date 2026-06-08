'use strict';
/* ══════════════════════════════════════════════════════
   Romania Crypto Signals — Real-time layer
   • Binance WebSocket live prices (instant, no polling lag)
   • Browser price alerts (localStorage + Notifications API)
   ══════════════════════════════════════════════════════ */

/* Map of the coins we stream from Binance. */
const RT_SYMBOLS = {
  BTC: 'btcusdt', ETH: 'ethusdt', SOL: 'solusdt', BNB: 'bnbusdt',
  XRP: 'xrpusdt', AVAX: 'avaxusdt', DOGE: 'dogeusdt', ADA: 'adausdt',
};
/* Reverse lookup: stream symbol -> short coin name. */
const RT_REVERSE = Object.fromEntries(Object.entries(RT_SYMBOLS).map(([k, v]) => [v, k]));

/* Live price store, updated by the websocket. { BTC:{price, change} } */
const RT_PRICES = {};
let _rtSocket = null;
let _rtReconnect = 0;

/**
 * Open (or reopen) the Binance combined ticker stream.
 * Falls back silently to the REST polling already running in app.js if it fails.
 */
function rtConnect() {
  const streams = Object.values(RT_SYMBOLS).map(s => `${s}@ticker`).join('/');
  const url = `wss://stream.binance.com:9443/stream?streams=${streams}`;
  try {
    _rtSocket = new WebSocket(url);
  } catch (_) { return; }

  _rtSocket.onopen = () => { _rtReconnect = 0; };

  _rtSocket.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (_) { return; }
    const d = msg.data; if (!d || !d.s) return;
    const coin = RT_REVERSE[d.s.toLowerCase()];
    if (!coin) return;
    const price = parseFloat(d.c);
    const change = parseFloat(d.P);
    RT_PRICES[coin] = { price, change };
    rtPaintTicker(coin, price, change);
    rtCheckAlerts(coin, price);
  };

  _rtSocket.onclose = () => {
    // Exponential-ish backoff, capped at 15s.
    _rtReconnect = Math.min(_rtReconnect + 1, 5);
    setTimeout(rtConnect, _rtReconnect * 3000);
  };
  _rtSocket.onerror = () => { try { _rtSocket.close(); } catch (_) {} };
}

/** Update the live ticker bar cells for one coin without a full re-render. */
function rtPaintTicker(coin, price, change) {
  const up = change >= 0;
  const html = `${fmtUsd(price)} <span class="${up ? 'tick-up' : 'tick-dn'}">${up ? '▲' : '▼'}${Math.abs(change).toFixed(2)}%</span>`;
  [document.getElementById('t-' + coin), document.getElementById('t-' + coin + '2')].forEach(el => { if (el) el.innerHTML = html; });
  // Keep paper-trading prices fresh too (app.js reads window.RT_PRICES as an override).
  if (typeof window !== 'undefined') window.RT_PRICES = RT_PRICES;
}

/* ── Price alerts ─────────────────────────────────────── */
const RT_ALERT_KEY = 'rcb_alerts_v1';
let _rtAlerts = rtLoadAlerts();

function rtLoadAlerts() {
  try { return JSON.parse(localStorage.getItem(RT_ALERT_KEY)) || []; } catch (_) { return []; }
}
function rtSaveAlerts() {
  localStorage.setItem(RT_ALERT_KEY, JSON.stringify(_rtAlerts));
  if (typeof Sync !== 'undefined' && Sync.isAuthed()) Sync.push({ alerts: _rtAlerts });
}

// Pull account alerts on login (overrides the local copy when present).
if (typeof Sync !== 'undefined') {
  Sync.onReady(async (authed) => {
    if (!authed) return;
    const remote = await Sync.pull();
    if (remote && Array.isArray(remote.alerts)) {
      _rtAlerts = remote.alerts;
      localStorage.setItem(RT_ALERT_KEY, JSON.stringify(_rtAlerts));
      rtRenderAlerts();
    } else {
      Sync.push({ alerts: _rtAlerts });
    }
  });
}

/**
 * Add a price alert.
 * @param {string} coin  short coin name (BTC, ETH…)
 * @param {('above'|'below')} dir  trigger direction
 * @param {number} target  target USD price
 */
function rtAddAlert(coin, dir, target) {
  if (!coin || !target || isNaN(target)) return;
  _rtAlerts.push({ id: Date.now(), coin, dir, target: +target, fired: false });
  rtSaveAlerts(); rtRenderAlerts();
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
}

function rtRemoveAlert(id) {
  _rtAlerts = _rtAlerts.filter(a => a.id !== id);
  rtSaveAlerts(); rtRenderAlerts();
}

/** Check live price against every active alert and fire matching ones. */
function rtCheckAlerts(coin, price) {
  let changed = false;
  _rtAlerts.forEach(a => {
    if (a.fired || a.coin !== coin) return;
    const hit = (a.dir === 'above' && price >= a.target) || (a.dir === 'below' && price <= a.target);
    if (hit) {
      a.fired = true; changed = true;
      rtFireAlert(a, price);
    }
  });
  if (changed) { rtSaveAlerts(); rtRenderAlerts(); }
}

function rtFireAlert(a, price) {
  const title = `🔔 ${a.coin} ${a.dir === 'above' ? 'peste' : 'sub'} ${fmtUsd(a.target)}`;
  const body = `Preț curent: ${fmtUsd(price)}`;
  if (typeof toast === 'function') toast('🔔', title, body, 'toast-gold');
  try {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, { body, icon: '/assets/rcb-logo.png' });
    }
  } catch (_) {}
}

/** Render the alerts list in the #alertsList container, if present. */
function rtRenderAlerts() {
  const el = document.getElementById('alertsList');
  if (!el) return;
  if (!_rtAlerts.length) {
    el.innerHTML = '<div class="pt-empty" data-i18n="alerts_empty">Nicio alertă activă. Adaugă una mai sus 👆</div>';
    if (typeof applyI18n === 'function') applyI18n();
    return;
  }
  el.innerHTML = _rtAlerts.map(a => `
    <div class="alert-item ${a.fired ? 'alert-fired' : ''}">
      <div class="alert-info">
        <span class="alert-coin">${a.coin}</span>
        <span class="alert-cond">${a.dir === 'above' ? '▲ peste' : '▼ sub'} <b>${fmtUsd(a.target)}</b></span>
        ${a.fired ? '<span class="alert-tag">✅ Declanșată</span>' : '<span class="alert-tag live">● Activă</span>'}
      </div>
      <button class="alert-del" onclick="rtRemoveAlert(${a.id})">✕</button>
    </div>`).join('');
}

/** Wire up the "add alert" form. */
function rtInitAlertForm() {
  const btn = document.getElementById('alertAddBtn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const coin = document.getElementById('alertCoin')?.value;
    const dir = document.getElementById('alertDir')?.value;
    const target = parseFloat(document.getElementById('alertPrice')?.value);
    if (!target || target <= 0) { if (typeof toast === 'function') toast('⚠️', 'Preț invalid', 'Introdu un preț țintă valid.'); return; }
    rtAddAlert(coin, dir, target);
    const inp = document.getElementById('alertPrice'); if (inp) inp.value = '';
    if (typeof toast === 'function') toast('✅', 'Alertă adăugată', `${coin} ${dir === 'above' ? 'peste' : 'sub'} ${fmtUsd(target)}`, 'toast-buy');
  });
  // Prefill the price field with the live price when the coin changes.
  const coinSel = document.getElementById('alertCoin');
  if (coinSel) coinSel.addEventListener('change', () => {
    const p = RT_PRICES[coinSel.value]?.price;
    const inp = document.getElementById('alertPrice');
    if (p && inp && !inp.value) inp.value = p.toFixed(2);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  rtConnect();
  rtInitAlertForm();
  rtRenderAlerts();
});
