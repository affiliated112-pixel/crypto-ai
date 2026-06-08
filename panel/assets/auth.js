/* Romania Crypto Signals — admin login / register page logic. */

function $(id) { return document.getElementById(id); }

function showMsg(el, text, ok) {
  el.textContent = text;
  el.className = 'auth-msg ' + (ok ? 'ok' : 'err');
}

/* tab switching */
document.querySelectorAll('.auth-tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.auth-tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    const which = tab.dataset.tab;
    $('loginForm').classList.toggle('hidden', which !== 'login');
    $('registerForm').classList.toggle('hidden', which !== 'register');
  });
});

/* if already logged in, go straight to dashboard */
(async function checkSession() {
  try {
    const r = await fetch('/api/me', { cache: 'no-store' });
    const d = await r.json();
    if (d.authenticated) window.location.href = '/?admin=1';
  } catch (e) { /* ignore */ }
})();

/* LOGIN */
$('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('loginMsg');
  showMsg(msg, 'Se verifică…', true);
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: $('loginUser').value, password: $('loginPass').value }),
    });
    const d = await res.json();
    if (d.ok) {
      showMsg(msg, '✅ Autentificare reușită! Redirecționare…', true);
      setTimeout(() => { window.location.href = '/?admin=1'; }, 600);
    } else {
      const left = d.attempts_left !== undefined ? ` (${d.attempts_left} încercări rămase)` : '';
      showMsg(msg, '❌ ' + (d.error || 'Eroare') + left, false);
    }
  } catch (err) {
    showMsg(msg, '❌ Eroare de conexiune.', false);
  }
});

/* REGISTER */
$('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('registerMsg');
  showMsg(msg, 'Se creează contul…', true);
  try {
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: $('regUser').value, password: $('regPass').value, code: $('regCode').value }),
    });
    const d = await res.json();
    if (d.ok) {
      showMsg(msg, '✅ ' + d.message + ' Acum te poți autentifica.', true);
    } else {
      showMsg(msg, '❌ ' + (d.message || 'Eroare'), false);
    }
  } catch (err) {
    showMsg(msg, '❌ Eroare de conexiune.', false);
  }
});

/* lightweight particle bg (shared look) */
(function bg() {
  const canvas = document.getElementById('bgCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w, h, parts;
  function resize() {
    w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight;
    parts = Array.from({ length: Math.min(50, Math.floor(w / 28)) }, () => ({
      x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4, r: Math.random() * 1.6 + 0.5,
    }));
  }
  resize(); window.addEventListener('resize', resize);
  (function tick() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i]; p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1; if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fillStyle = 'rgba(120,150,240,0.5)'; ctx.fill();
      for (let j = i + 1; j < parts.length; j++) {
        const q = parts[j], dx = p.x - q.x, dy = p.y - q.y, dist = Math.hypot(dx, dy);
        if (dist < 130) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.strokeStyle = `rgba(80,120,220,${0.12 * (1 - dist / 130)})`; ctx.stroke(); }
      }
    }
    requestAnimationFrame(tick);
  })();
})();
