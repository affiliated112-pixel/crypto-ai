/* Romania Crypto Signals — interactive live panel.
   Polls /api/stats and renders real data from the Discord bot + live market. */

const REFRESH_MS = 15000;
const DEFAULT_INVITE = 'https://discord.gg/'; // overridden by DISCORD_INVITE_URL env

/* ---------- helpers ---------- */
function fmt(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return Number(n).toLocaleString('ro-RO');
}
function fmtPrice(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Number(v);
  const dec = n >= 1000 ? 2 : n >= 1 ? 3 : 6;
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
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function setHref(id, url) { const el = document.getElementById(id); if (el && url) el.href = url; }

/* ---------- sparkline svg ---------- */
function sparkSvg(points, up) {
  if (!points || points.length < 2) return '';
  const w = 200, h = 40, min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const step = w / (points.length - 1);
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - ((p - min) / range) * h).toFixed(1)}`).join(' ');
  const color = up ? '#21d07a' : '#ff2d3f';
  return `<svg class="pc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round"/>
  </svg>`;
}

/* ---------- renderers ---------- */
function renderStatus(d) {
  const dot = document.getElementById('botStatusDot');
  const txt = document.getElementById('botStatusText');
  if (d.discord_ready) { dot.className = 'dot dot-on'; txt.textContent = 'Bot online'; }
  else { dot.className = 'dot dot-off'; txt.textContent = 'Bot offline'; }
}

function renderLinks(d) {
  const invite = (d.links && d.links.discord_invite) || DEFAULT_INVITE;
  ['heroDiscord', 'freeDiscord'].forEach((id) => setHref(id, invite));
  // VIP buttons → use invite too (the get-vip channel lives on Discord)
  ['navVip', 'vipCta', 'vipCta2'].forEach((id) => setHref(id, invite));
  const price = d.links && d.links.vip_price;
  if (price) setText('vipPriceSub', price);
}

function renderStats(d) {
  const s = d.server || {}, sig = d.signals || {}, coins = d.coins || {};
  setText('heroMembers', fmt(s.total_members));
  setText('heroSignals', fmt(sig.total));
  setText('heroVip', fmt(s.vip_members));
  setText('statMembers', fmt(s.total_members));
  setText('statOnline', fmt(s.online_members));
  setText('statVip', fmt(s.vip_members));
  setText('statSignals', fmt(sig.total));
  setText('statBuy', fmt(sig.buy));
  setText('statSell', fmt(sig.sell));
  setText('statCoins', fmt(coins.vip_count));
  setText('statToday', fmt((sig.today_free || 0) + (sig.today_vip || 0)));
  setText('lastUpdate', 'Actualizat ' + new Date(d.updated_at).toLocaleTimeString('ro-RO'));
}

function renderTicker(d) {
  const track = document.getElementById('tickerTrack');
  if (!track) return;
  const prices = (d.market && d.market.prices) || [];
  const vip = (d.market && d.market.vip_teaser) || [];
  const all = prices.concat(vip);
  if (!all.length) return;
  const item = (p) => {
    const up = (p.change || 0) >= 0;
    return `<span class="tick"><span class="tick-sym">${p.name}</span>
      <span class="tick-price">${fmtPrice(p.price)}</span>
      <span class="tick-chg ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${Math.abs(p.change || 0).toFixed(2)}%</span></span>`;
  };
  // duplicate for seamless loop
  track.innerHTML = (all.map(item).join('') + all.map(item).join(''));
}

function renderPrices(d) {
  const grid = document.getElementById('priceGrid');
  if (!grid) return;
  const prices = (d.market && d.market.prices) || [];
  if (!prices.length) { grid.innerHTML = '<div class="empty-card">Prețuri indisponibile momentan…</div>'; return; }
  grid.innerHTML = prices.map((p) => {
    const up = (p.change || 0) >= 0;
    return `<div class="price-card">
      <div class="pc-top"><span class="pc-sym">${p.name}</span>
        <span class="pc-chg ${up ? 'up' : 'down'}">${up ? '+' : ''}${(p.change || 0).toFixed(2)}%</span></div>
      <div class="pc-price">${fmtPrice(p.price)}</div>
      ${sparkSvg(p.spark, up)}
    </div>`;
  }).join('');
}

function renderFng(d) {
  const fng = (d.market && d.market.fear_greed) || {};
  const arc = document.getElementById('fngArc');
  const val = fng.value;
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
    <div class="sig-top">
      <div class="sig-coin"><b>${r.name || '—'}</b></div>
      <span class="badge ${buy ? 'badge-buy' : 'badge-sell'}">${r.side || '—'}</span>
    </div>
    <div class="sig-rows">
      <div class="sig-r"><span>Entry</span><b>${fmtPrice(r.entry)}</b></div>
      <div class="sig-r"><span>Scor calitate</span><b>${r.score ?? '—'}/100</b></div>
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
      <div class="sig-top">
        <div class="sig-coin"><b>${r.name || '••••'}</b></div>
        <span class="badge ${buy ? 'badge-buy' : 'badge-sell'}">${r.side || '••'}</span>
      </div>
      <div class="sig-rows">
        <div class="sig-r"><span>Entry</span><b>$••••••</b></div>
        <div class="sig-r"><span>TP1 / TP2 / TP3</span><b>••• / ••• / •••</b></div>
        <div class="sig-r"><span>Stop Loss</span><b>$••••••</b></div>
        <div class="sig-r"><span>Status</span><span class="badge badge-status">${r.status || '—'}</span></div>
      </div>
    </div>
    <div class="lock-overlay">
      <div class="lock-ic">🔒</div>
      <div class="lock-txt">Semnal VIP — ${r.name || 'Premium'} ${r.side || ''}</div>
      <a class="btn btn-vip-sm lock-btn" href="${invite}">💎 Deblochează</a>
    </div>
  </div>`;
}

function renderSignals(d) {
  const invite = (d.links && d.links.discord_invite) || DEFAULT_INVITE;
  const free = (d.signals && d.signals.free) || [];
  const vip = (d.signals && d.signals.vip) || [];

  const freeEl = document.getElementById('freeSignals');
  if (freeEl) {
    freeEl.innerHTML = free.length
      ? free.slice(0, 6).map(sigCardFree).join('')
      : '<div class="empty-card">Niciun semnal FREE încă. Botul îl va afișa imediat ce trimite unul.</div>';
  }

  const vipEl = document.getElementById('vipSignals');
  if (vipEl) {
    if (vip.length) {
      vipEl.innerHTML = vip.slice(0, 6).map((r) => sigCardVip(r, invite)).join('');
    } else {
      // show enticing locked placeholders even when none yet
      const placeholders = [
        { name: 'BTC', side: 'BUY', status: 'live' },
        { name: 'ETH', side: 'SELL', status: 'live' },
        { name: 'SOL', side: 'BUY', status: 'live' },
      ];
      vipEl.innerHTML = placeholders.map((r) => sigCardVip(r, invite)).join('');
    }
  }
}

function renderPerformance(d) {
  const p = d.performance || {};
  const winRate = Number(p.win_rate || 0);
  setText('perfWinRate', (p.win_rate !== undefined ? winRate.toFixed(0) : '—') + '%');
  setText('perfClosed', fmt(p.closed));
  setText('perfWins', fmt(p.wins));
  setText('perfLosses', fmt(p.losses));
  setText('perfOpen', fmt(p.open));
  const pnlEl = document.getElementById('perfPnl');
  if (pnlEl) {
    const pnl = p.avg_pnl_pct;
    if (pnl === undefined || pnl === null) { pnlEl.textContent = '—'; }
    else { const v = Number(pnl); pnlEl.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; pnlEl.className = v >= 0 ? 'pos' : 'neg'; }
  }
  const ring = document.getElementById('winRing');
  if (ring) {
    const deg = Math.max(0, Math.min(100, winRate)) * 3.6;
    const color = winRate >= 50 ? 'var(--green)' : winRate > 0 ? 'var(--yellow)' : 'rgba(255,255,255,0.06)';
    ring.style.background = `conic-gradient(${color} ${deg}deg, rgba(255,255,255,0.06) ${deg}deg)`;
  }
}

/* ---------- particle background ---------- */
function initParticles() {
  const canvas = document.getElementById('bgCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w, h, particles;
  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    const count = Math.min(70, Math.floor(w / 22));
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4, r: Math.random() * 1.8 + 0.6,
    }));
  }
  resize();
  window.addEventListener('resize', resize);
  function tick() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(120,150,240,0.5)'; ctx.fill();
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j], dx = p.x - q.x, dy = p.y - q.y, dist = Math.hypot(dx, dy);
        if (dist < 120) {
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(80,120,220,${0.12 * (1 - dist / 120)})`; ctx.lineWidth = 1; ctx.stroke();
        }
      }
    }
    requestAnimationFrame(tick);
  }
  tick();
}

/* ---------- main loop ---------- */
async function load() {
  try {
    const res = await fetch('/api/stats', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    renderStatus(d); renderLinks(d); renderStats(d);
    renderTicker(d); renderPrices(d); renderFng(d);
    renderSignals(d); renderPerformance(d);
  } catch (e) {
    const dot = document.getElementById('botStatusDot');
    const txt = document.getElementById('botStatusText');
    if (dot) dot.className = 'dot dot-off';
    if (txt) txt.textContent = 'Eroare conexiune';
    console.error('panel load error', e);
  }
}

initParticles();
load();
setInterval(load, REFRESH_MS);
