/* Romania Crypto Signals — 2026 Live Panel */
'use strict';

const REFRESH_MS = 15000;
const SCAN_INTERVAL = 900; // 15 min signal scan
const DEFAULT_INVITE = 'https://discord.gg/';

let _prevSignalTotal = null;
let _prevFree = [];
let _prevVip = [];
let _scanSecondsLeft = SCAN_INTERVAL;

/* ── helpers ─────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
function fmt(n) { if (n === null || n === undefined || isNaN(n)) return '—'; return Number(n).toLocaleString('ro-RO'); }
function fmtPrice(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Number(v), dec = n >= 1000 ? 2 : n >= 1 ? 3 : 6;
  return '$' + n.toLocaleString('en-US', { maximumFractionDigits: dec });
}
function timeAgo(ts) {
  if (!ts) return '—';
  const sec = Math.floor(Date.now() / 1000 - Number(ts));
  if (sec < 0) return 'acum';
  if (sec < 60) return `${sec}s în urmă`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m în urmă`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h în urmă`;
  return `${Math.floor(sec / 86400)}z în urmă`;
}
function setText(id, v) { const e = $(id); if (e) e.textContent = v; }
function setHref(id, url) { const e = $(id); if (e && url) e.href = url; }

/* ── counter animation ───────────────────────────── */
function animateCounter(el, target) {
  if (!el || isNaN(target)) return;
  const current = parseInt(el.textContent.replace(/[^0-9]/g, '')) || 0;
  if (current === target) { el.textContent = fmt(target); return; }
  const diff = target - current, duration = 1000, steps = 40;
  let step = 0;
  const interval = setInterval(() => {
    step++;
    const val = Math.round(current + diff * (step / steps));
    el.textContent = fmt(val);
    if (step >= steps) { clearInterval(interval); el.textContent = fmt(target); }
  }, duration / steps);
}

function updateCounters(d) {
  const s = d.server || {}, sig = d.signals || {};
  [['heroMembers', s.total_members], ['heroSignals', sig.total], ['heroVip', s.vip_members],
   ['statMembers', s.total_members], ['statVip', s.vip_members], ['statSignals', sig.total],
   ['statBuy', sig.buy], ['statSell', sig.sell]
  ].forEach(([id, val]) => {
    const el = $(id);
    if (el && val !== undefined) animateCounter(el, Number(val) || 0);
  });
}

/* ── sparkline svg ───────────────────────────────── */
function sparkSvg(pts, up) {
  if (!pts || pts.length < 2) return '';
  const w = 200, h = 40, mn = Math.min(...pts), mx = Math.max(...pts), rng = mx - mn || 1;
  const step = w / (pts.length - 1);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(h - ((p - mn) / rng) * h).toFixed(1)}`).join(' ');
  const col = up ? '#21d07a' : '#ff2d3f';
  const f = d + ` L${w},${h} L0,${h} Z`;
  return `<svg class="pc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="sg${up?'g':'r'}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".3"/>
      <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${f}" fill="url(#sg${up?'g':'r'})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>
  </svg>`;
}

/* ── toast notifications ─────────────────────────── */
function showToast(icon, title, msg, cls = '') {
  const c = $('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast ${cls}`;
  t.innerHTML = `<div class="toast-ic">${icon}</div><div class="toast-body"><div class="toast-title">${title}</div><div class="toast-msg">${msg}</div></div>`;
  c.appendChild(t);
  setTimeout(() => { t.classList.add('removing'); setTimeout(() => t.remove(), 320); }, 4500);
}

function checkNewSignals(d) {
  const total = (d.signals || {}).total;
  if (_prevSignalTotal !== null && total > _prevSignalTotal) {
    const diff = total - _prevSignalTotal;
    showToast('📡', `${diff} semnal${diff > 1 ? 'e noi' : ' nou'}!`, 'Bot-ul tocmai a trimis semnale noi.', 'toast-buy');
  }
  _prevSignalTotal = total;
}

/* ── scan countdown ──────────────────────────────── */
function initScanCountdown() {
  setInterval(() => {
    _scanSecondsLeft = Math.max(0, _scanSecondsLeft - 1);
    const el = $('scanCountdown');
    if (el) {
      const m = Math.floor(_scanSecondsLeft / 60), s = _scanSecondsLeft % 60;
      el.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    if (_scanSecondsLeft === 0) _scanSecondsLeft = SCAN_INTERVAL;
  }, 1000);
}

/* ── renderers ───────────────────────────────────── */
function renderStatus(d) {
  const dot = $('botStatusDot'), txt = $('botStatusText');
  if (d.discord_ready) { dot.className = 'dot dot-on'; txt.textContent = 'Bot online'; }
  else { dot.className = 'dot dot-off'; txt.textContent = 'Bot offline'; }
}

function renderLinks(d) {
  const inv = (d.links && d.links.discord_invite) || DEFAULT_INVITE;
  ['heroDiscord', 'freeDiscord'].forEach(id => setHref(id, inv));
  ['navVip', 'vipCta', 'vipCta2'].forEach(id => setHref(id, inv));
  const price = d.links && d.links.vip_price;
  if (price) setText('vipPriceSub', price);
}

function renderStats(d) {
  const s = d.server || {}, sig = d.signals || {}, coins = d.coins || {};
  setText('heroOnline', fmt(s.online_members));
  setText('statOnline', fmt(s.online_members));
  setText('statCoins', fmt(coins.vip_count));
  setText('statToday', fmt((sig.today_free || 0) + (sig.today_vip || 0)));
  setText('lastUpdate', 'Actualizat ' + new Date(d.updated_at).toLocaleTimeString('ro-RO'));
}

function renderTicker(d) {
  const track = $('tickerTrack');
  if (!track) return;
  const all = [...(d.market?.prices || []), ...(d.market?.vip_teaser || [])];
  if (!all.length) return;
  const item = (p) => {
    const up = (p.change || 0) >= 0;
    return `<span class="tick"><span class="tick-sym">${p.name}</span>
      <span class="tick-price">${fmtPrice(p.price)}</span>
      <span class="tick-chg ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${Math.abs(p.change || 0).toFixed(2)}%</span></span>`;
  };
  track.innerHTML = all.map(item).join('') + all.map(item).join('');
}

function renderPrices(d) {
  const grid = $('priceGrid');
  if (!grid) return;
  const prices = d.market?.prices || [];
  if (!prices.length) { grid.innerHTML = '<div class="empty-card" style="grid-column:1/-1">Prețuri indisponibile momentan…</div>'; return; }
  grid.innerHTML = prices.map(p => {
    const up = (p.change || 0) >= 0;
    return `<div class="price-card">
      <div class="pc-top"><span class="pc-sym">${p.name}</span>
        <span class="pc-chg ${up ? 'up' : 'down'}">${up ? '+' : ''}${(p.change || 0).toFixed(2)}%</span></div>
      <div class="pc-price">${fmtPrice(p.price)}</div>
      ${sparkSvg(p.spark, up)}
    </div>`;
  }).join('');

  // VIP tease coins
  const teaseEl = $('vipCoinsTease');
  const teaseCoins = d.market?.vip_teaser || [];
  if (teaseEl && teaseCoins.length) {
    teaseEl.innerHTML = teaseCoins.map(p => {
      const up = (p.change || 0) >= 0;
      return `<div class="vip-coin-tile">
        <span class="vct-name">${p.name}</span>
        <span class="vct-price">${fmtPrice(p.price)}</span>
        <span class="vct-chg ${up ? '' : 'neg'}">${up ? '+' : ''}${(p.change || 0).toFixed(2)}%</span>
      </div>`;
    }).join('');
  }
}

function renderFng(d) {
  const fng = d.market?.fear_greed || {};
  const arc = $('fngArc'), val = fng.value;
  setText('fngValue', val !== null && val !== undefined ? val : '—');
  setText('fngClass', fng.classification ? `Fear & Greed · ${fng.classification}` : 'Fear & Greed Index');
  if (arc && val !== null && val !== undefined) {
    const len = 283;
    arc.style.strokeDashoffset = String(len - (Math.max(0, Math.min(100, val)) / 100) * len);
  }
}

function sigCardFree(r) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card">
    <div class="sig-top"><div class="sig-coin"><b>${r.name || '—'}</b></div>
      <span class="badge ${buy ? 'badge-buy' : 'badge-sell'}">${r.side || '—'}</span></div>
    <div class="sig-rows">
      <div class="sig-r"><span>Entry</span><b>${fmtPrice(r.entry)}</b></div>
      <div class="sig-r"><span>Scor AI</span><b>${r.score ?? '—'}/100</b></div>
      <div class="sig-r"><span>R:R</span><b>${r.rr ? Number(r.rr).toFixed(2) : '—'}</b></div>
      <div class="sig-r"><span>Status</span><span class="badge badge-status">${r.status || '—'}</span></div>
    </div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)}</div>
  </div>`;
}

function sigCardVip(r, invite) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card locked">
    <div class="sig-blur">
      <div class="sig-top"><div class="sig-coin"><b>${r.name || '••••'}</b></div>
        <span class="badge ${buy ? 'badge-buy' : 'badge-sell'}">${r.side || '••'}</span></div>
      <div class="sig-rows">
        <div class="sig-r"><span>Entry</span><b>$•••••</b></div>
        <div class="sig-r"><span>TP1 / TP2 / TP3</span><b>••• / ••• / •••</b></div>
        <div class="sig-r"><span>Stop Loss</span><b>$•••••</b></div>
        <div class="sig-r"><span>Status</span><span class="badge badge-status">${r.status || '—'}</span></div>
      </div>
    </div>
    <div class="lock-overlay">
      <div class="lock-ic">🔒</div>
      <div class="lock-txt">${r.name || 'Premium'} ${r.side || ''} — VIP only</div>
      <a class="btn btn-vip-sm lock-btn" href="${invite}">💎 Deblochează</a>
    </div>
  </div>`;
}

function sigCardAdmin(r) {
  const buy = r.side === 'BUY';
  return `<div class="sig-card" style="border-color:rgba(255,184,0,.35)">
    <div class="sig-top">
      <div class="sig-coin"><b>${r.name || '—'}</b> <span class="badge badge-vip">VIP</span></div>
      <span class="badge ${buy ? 'badge-buy' : 'badge-sell'}">${r.side || '—'}</span>
    </div>
    <div class="sig-rows">
      <div class="sig-r"><span>Entry</span><b>${fmtPrice(r.entry)}</b></div>
      <div class="sig-r"><span>Scor AI</span><b>${r.score ?? '—'}/100</b></div>
      <div class="sig-r"><span>R:R</span><b>${r.rr ? Number(r.rr).toFixed(2) : '—'}</b></div>
      <div class="sig-r"><span>Stop Loss</span><b>${r.sl ? fmtPrice(r.sl) : '—'}</b></div>
      <div class="sig-r"><span>Status</span><span class="badge badge-status">${r.status || '—'}</span></div>
    </div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)}</div>
  </div>`;
}

function renderSignals(d) {
  const invite = d.links?.discord_invite || DEFAULT_INVITE;
  const free = d.signals?.free || [], vip = d.signals?.vip || [], isAdmin = !!d.is_admin;

  const freeEl = $('freeSignals');
  if (freeEl) freeEl.innerHTML = free.length
    ? free.slice(0, 6).map(sigCardFree).join('')
    : '<div class="empty-card">Niciun semnal FREE încă — botul va posta primul imediat.</div>';

  const vipEl = $('vipSignals');
  if (vipEl) {
    if (isAdmin) {
      vipEl.innerHTML = vip.length ? vip.slice(0, 6).map(sigCardAdmin).join('')
        : '<div class="empty-card">Niciun semnal VIP.</div>';
    } else if (vip.length) {
      vipEl.innerHTML = vip.slice(0, 6).map(r => sigCardVip(r, invite)).join('');
    } else {
      vipEl.innerHTML = [
        { name: 'BTC', side: 'BUY', status: 'live' },
        { name: 'ETH', side: 'SELL', status: 'live' },
        { name: 'SOL', side: 'BUY', status: 'live' },
      ].map(r => sigCardVip(r, invite)).join('');
    }
  }
}

function renderDiscord(d) {
  const s = d.server || {}, sig = d.signals || {};
  setText('dcServerName', s.name || 'Romania Crypto Signals');
  setText('dcMembers', fmt(s.total_members));
  setText('dcOnline', fmt(s.online_members));
  setText('dcVip', fmt(s.vip_members));
  setText('dcBots', fmt(s.bot_members));
  setText('dcText', fmt(s.text_channels));
  setText('dcVoice', fmt(s.voice_channels));
  setText('dcRoles', fmt(s.roles));
  setText('dcBoosts', fmt(s.boosts));

  // recent joins
  const joinList = $('dcJoinList');
  if (joinList) {
    const joins = s.recent_joins || [];
    joinList.innerHTML = joins.length
      ? joins.map(j => `<div class="dc-join-item">
          <span class="dc-join-name">👤 ${j.name}</span>
          <span class="dc-join-ago">${timeAgo(Date.now() / 1000 - j.joined_ago)}</span>
        </div>`).join('')
      : '<div class="dc-empty">Niciun membre nou în ultimele 24h.</div>';
  }

  // activity bars
  const total = Math.max(sig.buy + sig.sell, 1);
  const maxToday = Math.max((sig.today_free || 0) + (sig.today_vip || 0), 1);
  function setBar(barId, lblId, val, max) {
    const bar = $(barId), lbl = $(lblId);
    if (bar) bar.style.width = Math.min(100, Math.round((val / max) * 100)) + '%';
    if (lbl) lbl.textContent = fmt(val);
  }
  setBar('barBuy', 'lblBuy', sig.buy || 0, total);
  setBar('barSell', 'lblSell', sig.sell || 0, total);
  setBar('barFree', 'lblFree', sig.today_free || 0, maxToday);
  setBar('barVip', 'lblVip', sig.today_vip || 0, maxToday);
}

function renderPerformance(d) {
  const p = d.performance || {}, wr = Number(p.win_rate || 0);
  setText('perfWinRate', (p.win_rate !== undefined ? wr.toFixed(0) : '—') + '%');
  setText('perfClosed', fmt(p.closed)); setText('perfWins', fmt(p.wins));
  setText('perfLosses', fmt(p.losses)); setText('perfOpen', fmt(p.open));
  const pnlEl = $('perfPnl');
  if (pnlEl) {
    const pnl = p.avg_pnl_pct;
    if (pnl == null) { pnlEl.textContent = '—'; }
    else { const v = Number(pnl); pnlEl.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; pnlEl.className = v >= 0 ? 'pos' : 'neg'; }
  }
  const ring = $('winRing');
  if (ring) {
    const deg = Math.max(0, Math.min(100, wr)) * 3.6;
    const col = wr >= 50 ? 'var(--green)' : wr > 0 ? 'var(--yellow)' : 'rgba(255,255,255,.06)';
    ring.style.background = `conic-gradient(${col} ${deg}deg, rgba(255,255,255,.06) ${deg}deg)`;
  }
}

function renderAdmin(d) {
  const banner = $('adminBanner');
  if (!banner) return;
  if (d.is_admin) {
    banner.classList.remove('hidden');
    setText('adminName', d.admin_user || 'admin');
  } else {
    banner.classList.add('hidden');
  }
}

/* ── particle background ─────────────────────────── */
function initParticles() {
  const canvas = $('bgCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w, h, parts;
  function resize() {
    w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight;
    parts = Array.from({ length: Math.min(70, Math.floor(w / 22)) }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - .5) * .4, vy: (Math.random() - .5) * .4,
      r: Math.random() * 1.8 + .6,
    }));
  }
  resize(); window.addEventListener('resize', resize);
  (function tick() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i]; p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1; if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(120,150,240,.5)'; ctx.fill();
      for (let j = i + 1; j < parts.length; j++) {
        const q = parts[j], dx = p.x - q.x, dy = p.y - q.y, dist = Math.hypot(dx, dy);
        if (dist < 120) {
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(80,120,220,${.12 * (1 - dist / 120)})`; ctx.lineWidth = 1; ctx.stroke();
        }
      }
    }
    requestAnimationFrame(tick);
  })();
}

/* ── main data loop ──────────────────────────────── */
async function load() {
  try {
    const res = await fetch('/api/stats', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    renderStatus(d); renderLinks(d); renderStats(d); updateCounters(d);
    renderTicker(d); renderPrices(d); renderFng(d);
    renderSignals(d); renderDiscord(d); renderPerformance(d); renderAdmin(d);
    checkNewSignals(d);
  } catch (e) {
    const dot = $('botStatusDot'), txt = $('botStatusText');
    if (dot) dot.className = 'dot dot-off';
    if (txt) txt.textContent = 'Eroare conexiune';
    console.error('panel load error', e);
  }
}

/* ── logout handler ──────────────────────────────── */
document.addEventListener('click', async (e) => {
  if (e.target && e.target.id === 'adminLogout') {
    try { await fetch('/api/logout', { method: 'POST' }); } catch (_) {}
    window.location.href = '/';
  }
});

initParticles();
initScanCountdown();
load();
setInterval(load, REFRESH_MS);
