'use strict';
/* ══════════════════════════════════════════════════════════
   Romania Crypto Signals — 2025 ULTRA Panel JS
   ══════════════════════════════════════════════════════════ */

const REFRESH_MS    = 15_000;
const SCAN_INTERVAL = 900;
const DISCORD_LINK  = 'https://discord.gg/romaniacrypto';

let _prevTotal = null;
let _scanLeft  = SCAN_INTERVAL;
let _liveMarket = {};

/* ── utils ── */
const $  = (id) => document.getElementById(id);
const qs = (sel) => document.querySelector(sel);

function fmt(n) {
  if (n == null || isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('ro-RO');
}
function fmtUsd(v) {
  if (v == null || isNaN(Number(v))) return '—';
  const n = Number(v);
  const dec = n >= 1000 ? 2 : n >= 1 ? 3 : 6;
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function timeAgo(ts) {
  if (!ts) return '—';
  const s = Math.floor(Date.now() / 1000 - Number(ts));
  if (s < 0) return 'acum';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}z`;
}
function set(id, v) { const e = $(id); if (e) e.textContent = v; }

/* ── animated counter ── */
function animCount(el, target) {
  if (!el || isNaN(target)) return;
  const cur = parseInt(el.textContent.replace(/\D/g, '')) || 0;
  if (cur === target) { el.textContent = fmt(target); return; }
  const diff = target - cur, steps = 30;
  let i = 0;
  const t = setInterval(() => {
    i++;
    el.textContent = fmt(Math.round(cur + diff * (i / steps)));
    if (i >= steps) { clearInterval(t); el.textContent = fmt(target); }
  }, 900 / steps);
}

/* ── sparkline ── */
function spark(pts, up) {
  if (!pts || pts.length < 2) return '';
  const W = 180, H = 38, mn = Math.min(...pts), mx = Math.max(...pts), rng = mx - mn || 1;
  const step = W / (pts.length - 1);
  const d = pts.map((p, i) =>
    `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(H - ((p - mn) / rng) * (H - 4) - 2).toFixed(1)}`
  ).join(' ');
  const col = up ? '#00d97e' : '#ff2d55';
  const fill = d + ` L${W},${H} L0,${H} Z`;
  return `<svg class="pc-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="sg${up?'g':'r'}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".35"/>
      <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${fill}" fill="url(#sg${up?'g':'r'})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
}

/* ── toast ── */
function toast(icon, title, msg, cls = '') {
  const c = $('toastContainer'); if (!c) return;
  const t = document.createElement('div');
  t.className = `toast ${cls}`;
  t.innerHTML = `<div class="toast-ic">${icon}</div><div><div class="toast-title">${title}</div><div class="toast-msg">${msg}</div></div>`;
  c.appendChild(t);
  setTimeout(() => { t.classList.add('exit'); setTimeout(() => t.remove(), 320); }, 4500);
}

/* ── scan countdown ── */
(function scanTimer() {
  setInterval(() => {
    _scanLeft = Math.max(0, _scanLeft - 1);
    const el = $('scanTimer');
    if (el) {
      const m = Math.floor(_scanLeft / 60), s = _scanLeft % 60;
      el.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    if (_scanLeft === 0) _scanLeft = SCAN_INTERVAL;
  }, 1000);
})();

/* ── TradingView widget ── */
let _tvWidget = null;
function loadTVWidget(symbol = 'BINANCE:BTCUSDT') {
  const el = $('tvWidget'); if (!el) return;
  el.innerHTML = '';
  _tvWidget = new TradingView.widget({
    container_id: 'tvWidget',
    autosize: true,
    symbol,
    interval: '60',
    timezone: 'Europe/Bucharest',
    theme: 'dark',
    style: '1',
    locale: 'ro',
    toolbar_bg: '#090d1a',
    enable_publishing: false,
    allow_symbol_change: true,
    save_image: false,
    hide_side_toolbar: false,
    studies: ['RSI@tv-basicstudies', 'MACD@tv-basicstudies'],
    overrides: {
      'paneProperties.background': '#090d1a',
      'paneProperties.backgroundType': 'solid',
      'paneProperties.vertGridProperties.color': 'rgba(80,110,200,0.06)',
      'paneProperties.horzGridProperties.color': 'rgba(80,110,200,0.06)',
    },
  });
}

function changeChartSymbol() {
  const sel = $('chartSymbol'); if (!sel) return;
  if (_tvWidget) _tvWidget.setSymbol(sel.value, '60', () => {});
  else loadTVWidget(sel.value);
}

/* Load TV script */
(function loadTV() {
  if (typeof TradingView !== 'undefined') { loadTVWidget(); return; }
  const s = document.createElement('script');
  s.src = 'https://s3.tradingview.com/tv.js';
  s.onload = () => loadTVWidget();
  document.head.appendChild(s);
})();

/* ═══════════════════════════════════════════
   PAPER TRADING ENGINE
   ═══════════════════════════════════════════ */
const PT_INIT = 10_000;
const PT_KEY  = 'rcb_paper_v3';

let _pt = loadPT();
let _ptSide = 'LONG';
let _ptLev = 1;

function loadPT() {
  try { return JSON.parse(localStorage.getItem(PT_KEY)) || newPT(); }
  catch { return newPT(); }
}
function newPT() {
  return { cash: PT_INIT, positions: [], history: [], trades: 0, wins: 0 };
}
function savePT() { localStorage.setItem(PT_KEY, JSON.stringify(_pt)); }

function resetPaperTrading() {
  if (!confirm('Ești sigur? Portofoliul va fi resetat la $10,000.')) return;
  _pt = newPT(); savePT(); renderPT();
  toast('🔄', 'Reset!', 'Portofoliu resetat la $10,000 virtual.', 'toast-gold');
}

function setSide(s) {
  _ptSide = s;
  const btnL = $('btnLong'), btnS = $('btnShort'), submit = $('tfSubmit'), lbl = $('tfSubmitLabel');
  if (!btnL) return;
  btnL.className = 'tf-side-btn' + (s === 'LONG' ? ' active long-active' : '');
  btnS.className = 'tf-side-btn' + (s === 'SHORT' ? ' active short-active' : '');
  if (submit) submit.className = 'tf-submit' + (s === 'SHORT' ? ' short-mode' : '');
  if (lbl) lbl.textContent = s === 'LONG' ? '📈 Deschide LONG' : '📉 Deschide SHORT';
  updateTFSummary();
}

function setLev(v) {
  _ptLev = v;
  document.querySelectorAll('.lev-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.textContent) === v);
  });
  updateTFSummary();
}

function getPTPrice(coin) {
  const prices = _liveMarket.prices || [];
  const p = prices.find(x => x.name === coin || x.name === coin + '/USDT' || x.name.startsWith(coin));
  return p ? Number(p.price) : null;
}

function updatePaperPrice() {
  const coin = ($('ptCoin') || {}).value || 'BTC';
  const price = getPTPrice(coin);
  const el = $('tfPrice');
  if (el) el.textContent = price ? fmtUsd(price) : '—';
  updateTFSummary();
}

function updateTFSummary() {
  const coin = ($('ptCoin') || {}).value || 'BTC';
  const amount = parseFloat(($('ptAmount') || {}).value) || 0;
  const price  = getPTPrice(coin) || 0;
  const size   = amount * _ptLev;
  const qty    = price > 0 ? size / price : 0;
  const liqPct = _ptLev > 1 ? (1 / _ptLev) * 0.9 : 0;
  const liq    = _ptSide === 'LONG'
    ? price * (1 - liqPct)
    : price * (1 + liqPct);
  set('tfSize', size > 0 ? fmtUsd(size) + ` (${qty.toFixed(4)} ${coin})` : '—');
  set('tfLiq', price > 0 && _ptLev > 1 ? fmtUsd(liq) : 'N/A');
}

function openPosition() {
  const coin   = ($('ptCoin') || {}).value || 'BTC';
  const amount = parseFloat(($('ptAmount') || {}).value) || 0;
  const price  = getPTPrice(coin);
  if (!price) { toast('⚠️', 'Preț indisponibil', 'Prețul nu a fost încă încărcat.'); return; }
  if (amount < 10) { toast('⚠️', 'Sumă prea mică', 'Minim $10 per tranzacție.'); return; }
  if (amount > _pt.cash) { toast('❌', 'Fonduri insuficiente', `Ai doar ${fmtUsd(_pt.cash)} disponibil.`); return; }
  _pt.cash -= amount;
  _pt.positions.push({
    id: Date.now(), coin, side: _ptSide, lev: _ptLev,
    amount, entry: price, qty: (amount * _ptLev) / price,
    openedAt: Date.now(),
  });
  _pt.trades++;
  savePT(); renderPT();
  toast('🚀', `Poziție ${_ptSide} deschisă!`, `${amount.toFixed(0)}$ ${coin} la ${fmtUsd(price)} · ${_ptLev}x`, _ptSide === 'LONG' ? 'toast-buy' : 'toast-sell');
}

function closePosition(id) {
  const idx = _pt.positions.findIndex(p => p.id === id);
  if (idx === -1) return;
  const pos = _pt.positions[idx];
  const curPrice = getPTPrice(pos.coin) || pos.entry;
  const priceDiff = curPrice - pos.entry;
  const pnl = pos.side === 'LONG'
    ? (priceDiff / pos.entry) * pos.amount * pos.lev
    : (-priceDiff / pos.entry) * pos.amount * pos.lev;
  _pt.cash += pos.amount + pnl;
  if (pnl >= 0) _pt.wins++;
  _pt.history.unshift({
    coin: pos.coin, side: pos.side, lev: pos.lev,
    entry: pos.entry, exit: curPrice, pnl,
    closedAt: Date.now(),
  });
  if (_pt.history.length > 50) _pt.history.length = 50;
  _pt.positions.splice(idx, 1);
  savePT(); renderPT();
  const s = pnl >= 0 ? '✅' : '❌';
  toast(s, `Poziție închisă`, `${pos.coin} PnL: ${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)}`, pnl >= 0 ? 'toast-buy' : 'toast-sell');
}

function renderPT() {
  const prices = _liveMarket.prices || [];
  let positionsVal = 0;
  _pt.positions.forEach(p => {
    const cur = getPTPrice(p.coin) || p.entry;
    const priceDiff = cur - p.entry;
    const pnl = p.side === 'LONG'
      ? (priceDiff / p.entry) * p.amount * p.lev
      : (-priceDiff / p.entry) * p.amount * p.lev;
    positionsVal += p.amount + pnl;
  });
  const total = _pt.cash + positionsVal;
  const totalPnl = total - PT_INIT;

  const totalEl = $('ptTotal');
  if (totalEl) { totalEl.textContent = fmtUsd(total); }
  const pnlEl = $('ptPnl');
  if (pnlEl) {
    pnlEl.textContent = (totalPnl >= 0 ? '+' : '') + fmtUsd(totalPnl);
    pnlEl.className = 'pb-pnl-val ' + (totalPnl >= 0 ? 'pos' : 'neg');
  }
  set('ptCash', fmtUsd(_pt.cash));
  set('ptPositionsVal', fmtUsd(positionsVal));
  set('ptTrades', _pt.trades);
  const wr = _pt.trades > 0 ? Math.round((_pt.wins / (_pt.trades - _pt.positions.length || 1)) * 100) : null;
  set('ptWinrate', wr !== null ? wr + '%' : '—');

  // positions
  const posEl = $('ptPositions');
  if (posEl) {
    if (!_pt.positions.length) {
      posEl.innerHTML = '<div class="pt-empty">Nicio poziție deschisă</div>';
    } else {
      posEl.innerHTML = _pt.positions.map(p => {
        const cur = getPTPrice(p.coin) || p.entry;
        const priceDiff = cur - p.entry;
        const pnl = p.side === 'LONG'
          ? (priceDiff / p.entry) * p.amount * p.lev
          : (-priceDiff / p.entry) * p.amount * p.lev;
        return `<div class="position-item">
          <div class="pi-left">
            <span class="pi-coin">${p.coin} <span class="pi-side-tag ${p.side.toLowerCase()}">${p.side} ${p.lev}x</span></span>
            <span style="font-size:11px;color:var(--muted)">Entry: ${fmtUsd(p.entry)} · Cur: ${fmtUsd(cur)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="pi-pnl ${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)}</span>
            <button class="pi-close-btn" onclick="closePosition(${p.id})">Închide</button>
          </div>
        </div>`;
      }).join('');
    }
  }

  // history
  const hEl = $('ptHistory');
  if (hEl) {
    if (!_pt.history.length) {
      hEl.innerHTML = '<div class="pt-empty">Nicio tranzacție încă</div>';
    } else {
      hEl.innerHTML = _pt.history.map(h => `
        <div class="history-item">
          <div class="hi-top">
            <span class="hi-coin">${h.coin} <span class="pi-side-tag ${h.side.toLowerCase()}">${h.side} ${h.lev}x</span></span>
            <span class="hi-pnl ${h.pnl >= 0 ? 'pos' : 'neg'}">${h.pnl >= 0 ? '+' : ''}${fmtUsd(h.pnl)}</span>
          </div>
          <div class="hi-details">
            <span>Entry: ${fmtUsd(h.entry)}</span>
            <span>Exit: ${fmtUsd(h.exit)}</span>
            <span>${timeAgo(h.closedAt / 1000)} ago</span>
          </div>
        </div>`).join('');
    }
  }
}

/* ═══════════════════════════════════════════
   API RENDERERS
   ═══════════════════════════════════════════ */
function renderTicker(d) {
  const track = $('tickerTrack'); if (!track) return;
  const all = [...(d.market?.prices || []), ...(d.market?.vip_teaser || [])];
  if (!all.length) return;
  const item = (p) => {
    const up = (p.change || 0) >= 0;
    return `<span class="tick-item">${p.name} <b>${fmtUsd(p.price)}</b> <span class="${up ? 'tick-up' : 'tick-dn'}">${up ? '▲' : '▼'}${Math.abs(p.change || 0).toFixed(2)}%</span></span>`;
  };
  track.innerHTML = all.map(item).join('') + all.map(item).join('');
}

function renderFng(d) {
  const fng = d.market?.fear_greed || {};
  const val = fng.value;
  const numEl = $('fngNum'); if (numEl) numEl.textContent = val ?? '—';
  const arc = $('fngArc');
  if (arc && val != null) {
    const len = 283;
    arc.style.strokeDashoffset = String(len - (Math.max(0, Math.min(100, val)) / 100) * len);
  }
  const cls = $('fngClass');
  if (cls) {
    const label = fng.classification || '';
    cls.textContent = label ? `${label} (${val})` : 'Sentiment piață';
    const colors = { 'Extreme Fear': '#ff2d55', 'Fear': '#ff9800', 'Neutral': '#ffd02e', 'Greed': '#00d97e', 'Extreme Greed': '#00d97e' };
    cls.style.color = colors[label] || 'var(--text)';
  }
}

function renderPrices(d) {
  const area = $('pricesArea'); if (!area) return;
  const prices = d.market?.prices || [];
  if (!prices.length) return;
  area.innerHTML = prices.map(p => {
    const up = (p.change || 0) >= 0;
    return `<div class="price-card ${up ? 'up-card' : 'dn-card'}" onclick="quickChartCoin('${p.name}')">
      <div class="pc-header">
        <span class="pc-name">${p.name}</span>
        <span class="pc-badge ${up ? 'up' : 'dn'}">${up ? '+' : ''}${(p.change || 0).toFixed(2)}%</span>
      </div>
      <div class="pc-price">${fmtUsd(p.price)}</div>
      ${spark(p.spark, up)}
    </div>`;
  }).join('');

  const tease = $('vipTeaseRow');
  if (tease) {
    const vt = d.market?.vip_teaser || [];
    tease.innerHTML = vt.map(p => {
      const up = (p.change || 0) >= 0;
      return `<div class="vip-tease-tile">
        <span class="vtt-name">${p.name}</span>
        <span class="vtt-price">${fmtUsd(p.price)}</span>
        <span class="${up ? 'pos' : 'neg'}" style="font-size:12px;font-weight:700">${up ? '+' : ''}${(p.change || 0).toFixed(2)}%</span>
      </div>`;
    }).join('');
  }
}

function quickChartCoin(name) {
  const map = { BTC:'BINANCE:BTCUSDT', ETH:'BINANCE:ETHUSDT', SOL:'BINANCE:SOLUSDT', BNB:'BINANCE:BNBUSDT', XRP:'BINANCE:XRPUSDT' };
  const sym = map[name] || `BINANCE:${name}USDT`;
  const sel = $('chartSymbol'); if (sel) sel.value = sym;
  if (_tvWidget) _tvWidget.setSymbol(sym, '60', () => {});
  document.getElementById('chart')?.scrollIntoView({ behavior: 'smooth' });
}

function renderSignals(d) {
  const invite = d.links?.discord_invite || DISCORD_LINK;
  const free = d.signals?.free || [], vip = d.signals?.vip || [], isAdmin = !!d.is_admin;

  const freeEl = $('freeSignalGrid');
  if (freeEl) {
    freeEl.innerHTML = free.length
      ? free.slice(0, 6).map(r => sigCardFree(r)).join('')
      : '<div class="sig-empty">Bot-ul va posta primul semnal FREE în curând…</div>';
  }

  const vipEl = $('vipSignalGrid');
  if (vipEl) {
    if (isAdmin) {
      vipEl.innerHTML = vip.length
        ? vip.slice(0, 6).map(r => sigCardAdmin(r)).join('')
        : '<div class="sig-empty">Niciun semnal VIP momentan.</div>';
    } else if (vip.length) {
      vipEl.innerHTML = vip.slice(0, 6).map(r => sigCardLocked(r, invite)).join('');
    } else {
      vipEl.innerHTML = [
        { name: 'SOL', side: 'BUY', status: 'live' },
        { name: 'AVAX', side: 'BUY', status: 'live' },
        { name: 'DOT', side: 'SELL', status: 'live' },
      ].map(r => sigCardLocked(r, invite)).join('');
    }
  }
}

function sigCardFree(r) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card">
    <div class="sig-stripe stripe-${buy ? 'buy' : 'sell'}"></div>
    <div class="sig-top">
      <span class="sig-coin">${r.name || '—'}</span>
      <span class="sig-badge ${buy ? 'sig-badge-buy' : 'sig-badge-sell'}">${r.side || '—'}</span>
    </div>
    <div class="sig-row"><span>Entry</span><b>${fmtUsd(r.entry)}</b></div>
    <div class="sig-row"><span>Scor AI</span><b>${r.score ?? '—'}/100</b></div>
    <div class="sig-row"><span>R:R</span><b>${r.rr ? Number(r.rr).toFixed(2) : '—'}</b></div>
    <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status || '—'}</span></div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)} în urmă</div>
  </div>`;
}

function sigCardLocked(r, invite) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card sig-locked">
    <div class="sig-stripe stripe-vip"></div>
    <div class="sig-blur">
      <div class="sig-top">
        <span class="sig-coin">${r.name || '••••'}</span>
        <span class="sig-badge ${buy ? 'sig-badge-buy' : 'sig-badge-sell'}">${r.side || '••'}</span>
      </div>
      <div class="sig-row"><span>Entry</span><b>$•••••</b></div>
      <div class="sig-row"><span>TP1 / TP2 / TP3</span><b>••• / ••• / •••</b></div>
      <div class="sig-row"><span>Stop Loss</span><b>$•••••</b></div>
      <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status || '—'}</span></div>
    </div>
    <div class="sig-lock-overlay">
      <div class="slo-icon">🔒</div>
      <div class="slo-label">${r.name || 'VIP'} ${r.side} — Doar VIP</div>
      <a class="slo-btn" href="${invite}" target="_blank">💎 Deblochează — $25/lună</a>
    </div>
  </div>`;
}

function sigCardAdmin(r) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card" style="border-color:rgba(245,168,0,0.3)">
    <div class="sig-stripe stripe-vip"></div>
    <div class="sig-top">
      <span class="sig-coin">${r.name || '—'} <span class="sig-badge sig-badge-vip">VIP</span></span>
      <span class="sig-badge ${buy ? 'sig-badge-buy' : 'sig-badge-sell'}">${r.side || '—'}</span>
    </div>
    <div class="sig-row"><span>Entry</span><b>${fmtUsd(r.entry)}</b></div>
    <div class="sig-row"><span>Scor AI</span><b>${r.score ?? '—'}/100</b></div>
    <div class="sig-row"><span>R:R</span><b>${r.rr ? Number(r.rr).toFixed(2) : '—'}</b></div>
    <div class="sig-row"><span>Stop Loss</span><b>${r.sl ? fmtUsd(r.sl) : '—'}</b></div>
    <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status || '—'}</span></div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)} în urmă</div>
  </div>`;
}

function renderStats(d) {
  const s = d.server || {}, sig = d.signals || {}, coins = d.coins || {};
  animCount($('hcMembers'), Number(s.total_members) || 0);
  animCount($('hcSignals'), Number(sig.total) || 0);
  set('hcWinrate', (d.performance?.win_rate != null ? Number(d.performance.win_rate).toFixed(0) + '%' : '—'));
  set('hcOnline', fmt(s.online_members));
  animCount($('ssMembers'), Number(s.total_members) || 0);
  set('ssOnline', fmt(s.online_members));
  animCount($('ssVip'), Number(s.vip_members) || 0);
  animCount($('ssSignals'), Number(sig.total) || 0);
  animCount($('ssBuy'), Number(sig.buy) || 0);
  animCount($('ssSell'), Number(sig.sell) || 0);
  set('ssCoins', coins.vip_count ? fmt(coins.vip_count) : '30+');
  set('ssToday', fmt((sig.today_free || 0) + (sig.today_vip || 0)));
  set('updatedAt', 'Actualizat ' + new Date(d.updated_at || Date.now()).toLocaleTimeString('ro-RO'));
}

function renderStatus(d) {
  const dot = $('statusDot'), txt = $('statusText');
  if (!dot) return;
  if (d.discord_ready) {
    dot.classList.add('on');
    if (txt) txt.textContent = 'Bot online';
  } else {
    dot.classList.remove('on');
    if (txt) txt.textContent = 'Reconectare…';
  }
}

function renderAdmin(d) {
  const banner = $('adminBanner'); if (!banner) return;
  if (d.is_admin) {
    banner.classList.remove('hidden');
    set('adminName', d.admin_user || 'admin');
  } else {
    banner.classList.add('hidden');
  }
}

function renderPerformance(d) {
  const p = d.performance || {}, sig = d.signals || {};
  const wr = Number(p.win_rate || 0);
  set('perfWR', (p.win_rate != null ? wr.toFixed(0) : '—') + '%');
  set('perfClosed', fmt(p.closed));
  set('perfWins', fmt(p.wins));
  set('perfLosses', fmt(p.losses));
  set('perfOpen', fmt(p.open));
  const pnlEl = $('perfPnl');
  if (pnlEl) {
    const v = Number(p.avg_pnl_pct);
    if (isNaN(v)) { pnlEl.textContent = '—'; pnlEl.className = ''; }
    else { pnlEl.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; pnlEl.className = v >= 0 ? 'pos' : 'neg'; }
  }
  const ring = $('winRing');
  if (ring) {
    const deg = Math.max(0, Math.min(100, wr)) * 3.6;
    const col = wr >= 60 ? 'var(--green)' : wr >= 40 ? 'var(--gold)' : 'var(--red)';
    ring.style.background = `conic-gradient(${col} ${deg}deg, rgba(255,255,255,0.05) ${deg}deg)`;
  }
  const total = Math.max((sig.buy || 0) + (sig.sell || 0), 1);
  const todayMax = Math.max((sig.today_free || 0) + (sig.today_vip || 0), 1);
  function setBar(bId, lId, val, mx) {
    const b = $(bId); if (b) b.style.width = Math.min(100, Math.round((val / mx) * 100)) + '%';
    set(lId, fmt(val));
  }
  setBar('aBarBuy', 'aLblBuy', sig.buy || 0, total);
  setBar('aBarSell', 'aLblSell', sig.sell || 0, total);
  setBar('aBarFree', 'aLblFree', sig.today_free || 0, todayMax);
  setBar('aBarVip', 'aLblVip', sig.today_vip || 0, todayMax);
}

function renderDiscord(d) {
  const s = d.server || {};
  set('dcMembers', fmt(s.total_members));
  set('dcOnline', fmt(s.online_members));
  set('dcVip', fmt(s.vip_members));
  set('dcBots', fmt(s.bot_members));
  set('dcText', fmt(s.text_channels));
  set('dcVoice', fmt(s.voice_channels));
  set('dcBoosts', fmt(s.boosts));
  const joinEl = $('dcJoins');
  if (joinEl) {
    const joins = s.recent_joins || [];
    joinEl.innerHTML = joins.length
      ? joins.map(j => `<div class="dc-join-item"><span class="dc-join-name">👤 ${j.name}</span><span class="dc-join-ago">${timeAgo(Date.now() / 1000 - (j.joined_ago || 0))} ago</span></div>`).join('')
      : '<div class="dc-empty">Niciun membru nou în 24h</div>';
  }
}

function checkNewSignal(d) {
  const total = (d.signals || {}).total;
  if (_prevTotal !== null && total > _prevTotal) {
    const diff = total - _prevTotal;
    toast('📡', `${diff} semnal${diff > 1 ? 'e noi' : ' nou'}!`, 'Bot-ul tocmai a trimis semnale noi 🔥', 'toast-buy');
  }
  _prevTotal = total;
}

/* ═══════════════════════════════════════════
   PARTICLE BACKGROUND
   ═══════════════════════════════════════════ */
(function particles() {
  const canvas = $('bgCanvas'); if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w, h, pts;
  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    pts = Array.from({ length: Math.min(60, Math.floor(w / 24)) }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 1.5 + 0.5,
    }));
  }
  resize();
  window.addEventListener('resize', resize, { passive: true });
  (function draw() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(100,140,255,0.45)'; ctx.fill();
      for (let j = i + 1; j < pts.length; j++) {
        const q = pts[j], dx = p.x - q.x, dy = p.y - q.y, dist = Math.hypot(dx, dy);
        if (dist < 110) {
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(80,120,230,${0.1 * (1 - dist / 110)})`; ctx.lineWidth = 1; ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  })();
})();

/* navbar scroll shadow */
window.addEventListener('scroll', () => {
  const nav = document.querySelector('.navbar');
  if (nav) nav.style.boxShadow = window.scrollY > 20 ? '0 4px 32px rgba(0,0,0,0.5)' : '';
}, { passive: true });

/* logout */
document.addEventListener('click', async (e) => {
  if (e.target?.id === 'adminLogout') {
    try { await fetch('/api/logout', { method: 'POST' }); } catch (_) {}
    window.location.href = '/';
  }
});

/* ═══════════════════════════════════════════
   MAIN DATA LOOP
   ═══════════════════════════════════════════ */
async function load() {
  try {
    const res = await fetch('/api/stats', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    _liveMarket = d.market || {};
    renderStatus(d);
    renderStats(d);
    renderTicker(d);
    renderFng(d);
    renderPrices(d);
    renderSignals(d);
    renderPerformance(d);
    renderDiscord(d);
    renderAdmin(d);
    checkNewSignal(d);
    updatePaperPrice();
    renderPT();
  } catch (e) {
    const dot = $('statusDot');
    if (dot) dot.classList.remove('on');
    set('statusText', 'Eroare conexiune');
    console.error('panel load error', e);
  }
}

load();
setInterval(load, REFRESH_MS);
setInterval(renderPT, 5000); // update paper PnL every 5s
