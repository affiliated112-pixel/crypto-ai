/* Romania Crypto Signals — live panel front-end.
   Polls /api/stats and renders real data coming from the Discord bot. */

const REFRESH_MS = 15000;

function fmt(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return Number(n).toLocaleString('ro-RO');
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

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderStatus(data) {
  const dot = document.getElementById('botStatusDot');
  const txt = document.getElementById('botStatusText');
  if (!dot || !txt) return;
  if (data.discord_ready) {
    dot.className = 'dot dot-on';
    txt.textContent = 'Bot online';
  } else {
    dot.className = 'dot dot-off';
    txt.textContent = 'Bot offline';
  }
}

function renderStats(data) {
  const s = data.server || {};
  const sig = data.signals || {};
  const coins = data.coins || {};

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

  const upd = new Date(data.updated_at);
  setText('lastUpdate', 'Actualizat ' + upd.toLocaleTimeString('ro-RO'));
}

function renderPerformance(data) {
  const p = data.performance || {};
  const winRate = Number(p.win_rate || 0);
  setText('perfWinRate', (p.win_rate !== undefined ? winRate.toFixed(0) : '—') + '%');
  setText('perfClosed', fmt(p.closed));
  setText('perfWins', fmt(p.wins));
  setText('perfLosses', fmt(p.losses));
  setText('perfOpen', fmt(p.open));
  const pnl = p.avg_pnl_pct;
  const pnlEl = document.getElementById('perfPnl');
  if (pnlEl) {
    if (pnl === undefined || pnl === null) {
      pnlEl.textContent = '—';
    } else {
      const v = Number(pnl);
      pnlEl.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
      pnlEl.className = v >= 0 ? 'pos' : 'neg';
    }
  }
  const ring = document.getElementById('winRing');
  if (ring) {
    const deg = Math.max(0, Math.min(100, winRate)) * 3.6;
    const color = winRate >= 50 ? 'var(--green)' : winRate > 0 ? 'var(--yellow)' : 'rgba(255,255,255,0.06)';
    ring.style.background = `conic-gradient(${color} ${deg}deg, rgba(255,255,255,0.06) ${deg}deg)`;
  }
}

function renderSignals(data) {
  const body = document.getElementById('signalsBody');
  if (!body) return;
  const rows = data.recent_signals || [];
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">Niciun semnal încă. Botul va popula tabelul după primele semnale.</td></tr>';
    return;
  }
  body.innerHTML = rows.map((r) => {
    const side = (r.side || '').toUpperCase();
    const sideBadge = side === 'BUY'
      ? '<span class="badge badge-buy">BUY</span>'
      : side === 'SELL'
        ? '<span class="badge badge-sell">SELL</span>'
        : `<span class="badge badge-status">${side || '—'}</span>`;
    const tier = (r.tier || '').toLowerCase();
    const tierBadge = tier === 'vip'
      ? '<span class="badge badge-vip">VIP</span>'
      : '<span class="badge badge-free">FREE</span>';
    const entry = r.entry ? '$' + Number(r.entry).toLocaleString('en-US', { maximumFractionDigits: 6 }) : '—';
    return `<tr>
      <td class="coin-cell">${(r.symbol || '—').replace('USDT', '')}</td>
      <td>${sideBadge}</td>
      <td>${tierBadge}</td>
      <td>${entry}</td>
      <td>${r.score ?? '—'}</td>
      <td>${r.rr ? Number(r.rr).toFixed(2) : '—'}</td>
      <td><span class="badge badge-status">${r.status || '—'}</span></td>
      <td>${timeAgo(r.sent_at)}</td>
    </tr>`;
  }).join('');
}

async function load() {
  try {
    const res = await fetch('/api/stats', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderStatus(data);
    renderStats(data);
    renderPerformance(data);
    renderSignals(data);
  } catch (e) {
    const dot = document.getElementById('botStatusDot');
    const txt = document.getElementById('botStatusText');
    if (dot) dot.className = 'dot dot-off';
    if (txt) txt.textContent = 'Eroare conexiune';
    console.error('panel load error', e);
  }
}

load();
setInterval(load, REFRESH_MS);
