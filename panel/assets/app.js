'use strict';
/* ══════════════════════════════════════════════════════
   Romania Crypto Signals — 2025 App JS
   ══════════════════════════════════════════════════════ */

const REFRESH_MS = 15000;
const DISCORD    = 'https://discord.gg/romaniacrypto';
let _market = {};
let _prevTotal = null;
let _scanLeft = 900;

// ── Binance REST fallback prices (used when /api/stats has no data) ──────────
// { BTC: {price, change}, ETH: ... }
const _DIRECT_PRICES = {};
const _BINANCE_SYMBOLS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','AVAXUSDT','DOGEUSDT','ADAUSDT'];
let _directFetchBusy = false;

async function _fetchDirectPrices() {
  if (_directFetchBusy) return;
  _directFetchBusy = true;
  try {
    const url = 'https://api.binance.com/api/v3/ticker/24hr?symbols=' +
      encodeURIComponent(JSON.stringify(_BINANCE_SYMBOLS));
    const r = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const arr = await r.json();
    arr.forEach(t => {
      const name = t.symbol.replace('USDT', '');
      _DIRECT_PRICES[name] = {
        name,
        price: +t.lastPrice,
        change: +t.priceChangePercent,
        high: +t.highPrice,
        low: +t.lowPrice,
        volume: +t.quoteVolume,
        spark: [],
      };
    });
  } catch (_) {
    // Try Binance.US as second fallback
    try {
      const url2 = 'https://api.binance.us/api/v3/ticker/24hr?symbols=' +
        encodeURIComponent(JSON.stringify(_BINANCE_SYMBOLS));
      const r2 = await fetch(url2, { signal: AbortSignal.timeout(6000) });
      if (r2.ok) {
        const arr2 = await r2.json();
        arr2.forEach(t => {
          const name = t.symbol.replace('USDT', '');
          _DIRECT_PRICES[name] = { name, price: +t.lastPrice, change: +t.priceChangePercent, high: +t.highPrice, low: +t.lowPrice, volume: +t.quoteVolume, spark: [] };
        });
      }
    } catch (_2) {}
  } finally {
    _directFetchBusy = false;
  }
}

// Fetch direct prices immediately on load, then every 15s.
// After first fetch resolves, paint the market section right away
// (before /api/stats returns, so the page is never empty).
_fetchDirectPrices().then(() => {
  if(Object.keys(_DIRECT_PRICES).length) {
    renderPrices({market:{prices:Object.values(_DIRECT_PRICES)}});
    renderTicker({market:{prices:Object.values(_DIRECT_PRICES)}});
  }
});
setInterval(() => {
  _fetchDirectPrices().then(() => {
    // Re-paint only if /api/stats hasn't already provided server prices.
    if(!(_market.prices&&_market.prices.length) && Object.keys(_DIRECT_PRICES).length) {
      renderPrices({market:{prices:Object.values(_DIRECT_PRICES)}});
      renderTicker({market:{prices:Object.values(_DIRECT_PRICES)}});
    }
  });
}, 15000);

// ── Helpers ──────────────────────────────────────────
const $  = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);
function set(id, v) { const e=$(id); if(e) e.textContent=v; }
function fmt(n) { if(n==null||isNaN(+n)) return '—'; return (+n).toLocaleString('ro-RO'); }
function fmtUsd(v) {
  if(v==null||isNaN(+v)) return '—';
  const n=+v, d=n>=1000?2:n>=1?3:6;
  return '$'+n.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
}
function timeAgo(ts) {
  if(!ts) return '—';
  const s=Math.floor(Date.now()/1000-+ts);
  if(s<60) return s+'s';
  if(s<3600) return Math.floor(s/60)+'m';
  if(s<86400) return Math.floor(s/3600)+'h';
  return Math.floor(s/86400)+'z';
}

// ── Animated counter ─────────────────────────────────
function animCount(el, target) {
  if(!el||isNaN(target)) return;
  const cur=parseInt((el.textContent||'').replace(/\D/g,''))||0;
  if(cur===+target){el.textContent=fmt(target);return;}
  const diff=+target-cur, steps=28; let i=0;
  const t=setInterval(()=>{
    i++;el.textContent=fmt(Math.round(cur+diff*(i/steps)));
    if(i>=steps){clearInterval(t);el.textContent=fmt(+target);}
  },1000/steps);
}

// ── Sparkline ────────────────────────────────────────
function sparkline(pts, up) {
  if(!pts||pts.length<2) return '';
  const W=160,H=36,mn=Math.min(...pts),mx=Math.max(...pts),rng=mx-mn||1;
  const step=W/(pts.length-1);
  const d=pts.map((p,i)=>`${i?'L':'M'}${(i*step).toFixed(1)},${(H-((p-mn)/rng)*(H-4)-2).toFixed(1)}`).join(' ');
  const col=up?'#00d47e':'#ff2d55';
  const fill=d+` L${W},${H} L0,${H} Z`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:36px;display:block" preserveAspectRatio="none">
    <defs><linearGradient id="sg${up?'u':'d'}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".3"/>
      <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${fill}" fill="url(#sg${up?'u':'d'})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round"/>
  </svg>`;
}

// ── Toast ────────────────────────────────────────────
function toast(icon, title, msg, cls='') {
  const c=$('toastContainer'); if(!c) return;
  const el=document.createElement('div');
  el.className='toast '+cls;
  el.innerHTML=`<span class="toast-ic">${icon}</span><div><div class="toast-title">${title}</div><div class="toast-msg">${msg}</div></div>`;
  c.appendChild(el);
  setTimeout(()=>{el.classList.add('exit');setTimeout(()=>el.remove(),300);},4500);
}

// ── Scan countdown ───────────────────────────────────
setInterval(()=>{
  _scanLeft=Math.max(0,_scanLeft-1);
  const el=$('scanTimer');
  if(el){const m=Math.floor(_scanLeft/60),s=_scanLeft%60;el.textContent=`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;}
  if(_scanLeft===0) _scanLeft=900;
},1000);

// ── Navbar scroll shadow ─────────────────────────────
window.addEventListener('scroll',()=>{
  const n=$('navbar');
  if(n) n.style.boxShadow=window.scrollY>10?'0 4px 32px rgba(0,0,0,0.5)':'';
},{passive:true});

// ── Mobile menu ──────────────────────────────────────
function toggleMobileMenu(){
  const m=$('navMenu');
  if(m) m.classList.toggle('mobile-open');
}
// Close the mobile menu after tapping a navigation link.
document.addEventListener('click',e=>{
  const link=e.target.closest('.nav-menu .nav-item');
  if(link){const m=$('navMenu');if(m) m.classList.remove('mobile-open');}
});

// ── Logout ───────────────────────────────────────────
document.addEventListener('click',async e=>{
  if(e.target?.id==='adminLogout'){
    try{await fetch('/api/logout',{method:'POST'});}catch(_){}
    window.location.reload();
  }
});

// ══════════════════════════════════════════════════════
// NEWS FEED  (CoinGecko / RSS via allorigins proxy)
// ══════════════════════════════════════════════════════
const NEWS_FEEDS = [
  'https://www.coindesk.com/arc/outboundfeeds/rss/',
  'https://cointelegraph.com/rss',
  'https://decrypt.co/feed',
];
let _newsLoaded = false;

async function loadNews(force) {
  const grid=$('newsGrid'); if(!grid) return;
  if(_newsLoaded && !force) return;
  grid.innerHTML='<div class="news-skel"></div>'.repeat(6);
  const articles=[];
  for(const feed of NEWS_FEEDS){
    try{
      const proxy=`https://api.allorigins.win/get?url=${encodeURIComponent(feed)}`;
      const res=await fetch(proxy,{signal:AbortSignal.timeout(8000)});
      const j=await res.json();
      const parser=new DOMParser();
      const doc=parser.parseFromString(j.contents,'text/xml');
      const items=[...doc.querySelectorAll('item')].slice(0,4);
      let source='Crypto News';
      try{source=new URL(feed).hostname.replace('www.','').split('.')[0];source=source.charAt(0).toUpperCase()+source.slice(1);}catch(_){}
      items.forEach(item=>{
        const title=item.querySelector('title')?.textContent?.trim();
        const link=item.querySelector('link')?.textContent?.trim();
        const pub=item.querySelector('pubDate')?.textContent?.trim();
        const desc=item.querySelector('description')?.textContent?.replace(/<[^>]+>/g,'')?.trim()?.slice(0,120);
        if(title&&link) articles.push({title,link,pub,desc,source});
      });
    }catch(_){}
  }
  if(!articles.length){
    grid.innerHTML=`<div class="news-error">📰 Știrile se vor încărca în câteva secunde — încearcă din nou.</div>`;
    return;
  }
  grid.innerHTML=articles.slice(0,6).map(a=>{
    const ts=a.pub?new Date(a.pub).toLocaleString('ro-RO',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'';
    return `<a class="news-card" href="${a.link}" target="_blank" rel="noopener">
      <div class="news-source">📰 ${a.source||'Crypto News'}</div>
      <div class="news-title">${a.title}</div>
      <div class="news-desc">${a.desc||''}</div>
      <div class="news-time">${ts}</div>
    </a>`;
  }).join('');
  _newsLoaded=true;
}

// ══════════════════════════════════════════════════════
// PAPER TRADING ENGINE
// ══════════════════════════════════════════════════════
const PT_KEY='rcb_pt_v4', PT_INIT=10000;
let _pt=loadPT(), _ptSide='LONG', _ptLev=1;

function loadPT(){ try{return JSON.parse(localStorage.getItem(PT_KEY))||newPT();}catch{return newPT();} }
function newPT(){ return{cash:PT_INIT,positions:[],history:[],trades:0,wins:0,losses:0}; }
function savePT(){
  localStorage.setItem(PT_KEY,JSON.stringify(_pt));
  // Mirror to the user's account when logged in (debounced inside Sync).
  if(typeof Sync!=='undefined'&&Sync.isAuthed()) Sync.push({paper:_pt});
}

// On load, if the user is authenticated and has account data, prefer it over localStorage.
if(typeof Sync!=='undefined'){
  Sync.onReady(async (authed)=>{
    if(!authed) return;
    const remote=await Sync.pull();
    if(remote&&remote.paper&&typeof remote.paper==='object'){
      _pt=remote.paper;
      localStorage.setItem(PT_KEY,JSON.stringify(_pt));
      if(typeof renderPT==='function') renderPT();
    } else {
      // First login on this account — seed the account with local data.
      Sync.push({paper:_pt});
    }
    // Show a small badge that sync is active.
    const chip=document.getElementById('syncChip');
    if(chip){chip.textContent='☁️ Sincronizat cu contul';chip.style.display='inline-flex';}
  });
}

function resetPT(){
  if(!confirm('Resetezi portofoliul la $10,000. Ești sigur?')) return;
  _pt=newPT(); savePT(); renderPT();
  toast('🔄','Reset!','Portofoliu resetat la $10,000 virtual.','toast-gold');
}

function getPrice(coin){
  // 1. Prefer the live websocket price (realtime.js) — sub-100ms latency.
  const live=(typeof window!=='undefined'&&window.RT_PRICES&&window.RT_PRICES[coin])?window.RT_PRICES[coin].price:null;
  if(live!=null&&!isNaN(live)) return +live;
  // 2. Server-side REST price from /api/stats.
  const p=(_market.prices||[]).find(x=>x.name===coin||x.name.startsWith(coin));
  if(p&&p.price) return +p.price;
  // 3. Direct Binance REST fallback (fetched client-side).
  const d=_DIRECT_PRICES[coin];
  if(d&&d.price) return +d.price;
  return null;
}

function setSide(s){
  _ptSide=s;
  const bl=$('btnLong'),bs=$('btnShort'),sub=$('tfSubmit'),lbl=$('tfLabel');
  if(!bl) return;
  bl.className='tf-side'+(s==='LONG'?' long-active':'');
  bs.className='tf-side'+(s==='SHORT'?' short-active':'');
  if(sub) sub.className='tf-submit'+(s==='SHORT'?' short-mode':'');
  if(lbl) lbl.textContent=s==='LONG'?'📈 Deschide LONG':'📉 Deschide SHORT';
  updateSummary();
}

function setLev(btn,v){
  _ptLev=v;
  document.querySelectorAll('.lev-btn').forEach(b=>b.classList.remove('lev-active'));
  btn.classList.add('lev-active');
  updateSummary();
}

function onCoinChange(){ updateSummary(); const c=($('ptCoin')||{}).value; set('tfPrice',c?fmtUsd(getPrice(c)):'—'); }

function updateSummary(){
  const coin=($('ptCoin')||{}).value||'BTC';
  const amt=parseFloat(($('ptAmt')||{}).value)||0;
  const price=getPrice(coin)||0;
  const size=amt*_ptLev;
  const liqPct=_ptLev>1?(1/_ptLev)*0.85:0;
  const liq=_ptSide==='LONG'?price*(1-liqPct):price*(1+liqPct);
  set('tfSize',size>0?fmtUsd(size)+` (${(size/price||0).toFixed(4)} ${coin})`:'—');
  set('tfLiq',price>0&&_ptLev>1?fmtUsd(liq):'N/A');
}

function openPosition(){
  const coin=($('ptCoin')||{}).value||'BTC';
  const amt=parseFloat(($('ptAmt')||{}).value)||0;
  let price=getPrice(coin);

  // If price still null, try one more time to refresh direct prices then abort.
  if(!price){
    toast('⏳','Se încască prețul…','Așteaptă 2 secunde, se fetch-uiesc prețurile direct din Binance.','toast-gold');
    _fetchDirectPrices().then(()=>{
      const retry=getPrice(coin);
      if(retry){
        // Re-submit automatically after fetch
        setTimeout(()=>{ if(getPrice(coin)) openPosition(); },200);
      } else {
        toast('⚠️','Preț indisponibil','Verifici conexiunea la internet? Binance API inaccesibil.');
      }
    });
    return;
  }
  if(amt<10){toast('⚠️','Sumă prea mică','Minim $10 per poziție.');return;}
  if(amt>_pt.cash){toast('❌','Fonduri insuficiente',`Ai doar ${fmtUsd(_pt.cash)} disponibil.`);return;}
  _pt.cash-=amt;
  _pt.positions.push({id:Date.now(),coin,side:_ptSide,lev:_ptLev,amt,entry:price,qty:(amt*_ptLev)/price,openedAt:Date.now()});
  _pt.trades++;
  savePT(); renderPT();
  toast(_ptSide==='LONG'?'📈':'📉',`${_ptSide} ${coin} deschis!`,`${fmtUsd(amt)} · ${_ptLev}x · Entry: ${fmtUsd(price)}`,_ptSide==='LONG'?'toast-buy':'toast-sell');
}

function closePosition(id){
  const idx=_pt.positions.findIndex(p=>p.id===id); if(idx===-1) return;
  const pos=_pt.positions[idx];
  const cur=getPrice(pos.coin)||pos.entry;
  const diff=cur-pos.entry;
  const pnl=pos.side==='LONG'?(diff/pos.entry)*pos.amt*pos.lev:(-diff/pos.entry)*pos.amt*pos.lev;
  _pt.cash+=pos.amt+pnl;
  if(pnl>=0) _pt.wins++; else _pt.losses++;
  _pt.history.unshift({coin:pos.coin,side:pos.side,lev:pos.lev,entry:pos.entry,exit:cur,pnl,closedAt:Date.now()});
  if(_pt.history.length>50) _pt.history.length=50;
  _pt.positions.splice(idx,1);
  savePT(); renderPT();
  toast(pnl>=0?'✅':'❌',`Poziție închisă`,`${pos.coin} PnL: ${pnl>=0?'+':''}${fmtUsd(pnl)}`,pnl>=0?'toast-buy':'toast-sell');
}

function renderPT(){
  const prices=_market.prices||[];
  let posVal=0;
  _pt.positions.forEach(p=>{
    const cur=getPrice(p.coin)||p.entry;
    const diff=cur-p.entry;
    const pnl=p.side==='LONG'?(diff/p.entry)*p.amt*p.lev:(-diff/p.entry)*p.amt*p.lev;
    posVal+=p.amt+pnl;
  });
  const total=_pt.cash+posVal;
  const totalPnl=total-PT_INIT;

  const totalEl=$('ptTotal'); if(totalEl) totalEl.textContent=fmtUsd(total);
  const pnlEl=$('ptPnl');
  if(pnlEl){pnlEl.textContent=(totalPnl>=0?'+':'')+fmtUsd(totalPnl);pnlEl.className='pt-bal-pnl '+(totalPnl>=0?'pos':'neg');}
  set('ptCash',fmtUsd(_pt.cash));
  set('ptPosVal',fmtUsd(posVal));
  set('ptTrades',_pt.trades);
  const closed=_pt.wins+_pt.losses;
  set('ptWR',closed>0?Math.round((_pt.wins/closed)*100)+'%':'—');

  // Positions
  const posEl=$('ptPositions');
  if(posEl){
    if(!_pt.positions.length){posEl.innerHTML='<div class="pt-empty">Nicio poziție deschisă</div>';}
    else{posEl.innerHTML=_pt.positions.map(p=>{
      const cur=getPrice(p.coin)||p.entry;
      const diff=cur-p.entry;
      const pnl=p.side==='LONG'?(diff/p.entry)*p.amt*p.lev:(-diff/p.entry)*p.amt*p.lev;
      return `<div class="pos-item">
        <div>
          <span class="pos-coin">${p.coin}</span>
          <span class="pos-tag ${p.side==='LONG'?'long':'short'}">${p.side} ${p.lev}x</span>
          <div style="font-size:11px;color:var(--muted);margin-top:2px">Entry ${fmtUsd(p.entry)}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="${pnl>=0?'pos':'neg'}" style="font-family:'JetBrains Mono',monospace;font-weight:800">${pnl>=0?'+':''}${fmtUsd(pnl)}</span>
          <button class="pi-close-btn" onclick="closePosition(${p.id})">✕</button>
        </div>
      </div>`;
    }).join('');}
  }

  // History
  const hEl=$('ptHistory');
  if(hEl){
    if(!_pt.history.length){hEl.innerHTML='<div class="pt-empty">Nicio tranzacție încă. Deschide prima ta poziție!</div>';}
    else{hEl.innerHTML=_pt.history.map(h=>`
      <div class="history-item">
        <div class="hi-top">
          <span class="pos-coin">${h.coin} <span class="pos-tag ${h.side==='LONG'?'long':'short'}" style="font-size:9px">${h.side} ${h.lev}x</span></span>
          <span class="${h.pnl>=0?'pos':'neg'}" style="font-family:'JetBrains Mono',monospace;font-weight:800">${h.pnl>=0?'+':''}${fmtUsd(h.pnl)}</span>
        </div>
        <div class="hi-meta">
          <span>Entry: ${fmtUsd(h.entry)}</span>
          <span>Exit: ${fmtUsd(h.exit)}</span>
          <span>${timeAgo(h.closedAt/1000)} ago</span>
        </div>
      </div>`).join('');}
  }

  // Update live price display
  const coin=($('ptCoin')||{}).value;
  if(coin) set('tfPrice',fmtUsd(getPrice(coin)));
  updateSummary();
}

// ══════════════════════════════════════════════════════
// DATA RENDERERS
// ══════════════════════════════════════════════════════
function renderStatus(d){
  const dot=$('statusDot'),txt=$('statusText');
  if(!dot) return;
  if(d.discord_ready){dot.className='status-dot on';if(txt) txt.textContent='Bot online';}
  else{dot.className='status-dot';if(txt) txt.textContent='Reconectare…';}
}

function renderTicker(d){
  const serverPrices=d.market?.prices||[];
  const COINS=['BTC','ETH','SOL','BNB','XRP','AVAX','DOGE','ADA'];
  COINS.forEach(sym=>{
    // Skip if realtime.js already painted this coin via WebSocket.
    if(window.RT_PRICES&&window.RT_PRICES[sym]) return;
    const p=serverPrices.find(x=>x.name===sym||x.name.startsWith(sym))||_DIRECT_PRICES[sym];
    if(!p) return;
    const up=(p.change||0)>=0;
    const val=`${fmtUsd(p.price)} <span class="${up?'tick-up':'tick-dn'}">${up?'▲':'▼'}${Math.abs(p.change||0).toFixed(2)}%</span>`;
    [$('t-'+sym),$('t-'+sym+'2')].forEach(el=>{if(el) el.innerHTML=val;});
  });
}

function renderFng(d){
  const fg=d.market?.fear_greed||{};
  const val=fg.value; if(val==null) return;
  set('fngNum',val);
  const arc=$('fngArc');
  if(arc){ const offset=283-Math.max(0,Math.min(100,val))/100*283; arc.style.strokeDashoffset=String(offset); }
  const cl=$('fngClass');
  if(cl){
    cl.textContent=fg.classification||'';
    const C={'Extreme Fear':'#ff2d55','Fear':'#f5a800','Neutral':'#ffd02e','Greed':'#22c55e','Extreme Greed':'#00d47e'};
    cl.style.color=C[fg.classification]||'var(--text)';
  }
}

function renderPrices(d){
  const area=$('pricesArea'); if(!area) return;
  // Use server prices when available, otherwise fall back to direct Binance prices.
  let prices=d.market?.prices||[];
  if(!prices.length && Object.keys(_DIRECT_PRICES).length) {
    prices = Object.values(_DIRECT_PRICES);
  }
  if(!prices.length) return;
  area.innerHTML=prices.slice(0,6).map(p=>{
    const up=(p.change||0)>=0;
    return `<div class="price-card ${up?'up-card':'dn-card'}" onclick="quickChart('${p.name}')">
      <div class="pc-header"><span class="pc-name">${p.name}</span><span class="pc-badge ${up?'up':'dn'}">${up?'+':''}${(p.change||0).toFixed(2)}%</span></div>
      <div class="pc-price">${fmtUsd(p.price)}</div>
      ${sparkline(p.spark,up)}
    </div>`;
  }).join('');
}

function quickChart(coin){
  const map={BTC:'BINANCE:BTCUSDT',ETH:'BINANCE:ETHUSDT',SOL:'BINANCE:SOLUSDT',BNB:'BINANCE:BNBUSDT',XRP:'BINANCE:XRPUSDT'};
  const sel=$('chartSymbol');
  const sym=map[coin]||`BINANCE:${coin}USDT`;
  if(sel){sel.value=sym; changeChartSymbol(sym);}
  document.getElementById('chart')?.scrollIntoView({behavior:'smooth'});
}

function renderStats(d){
  const s=d.server||{},sig=d.signals||{};
  animCount($('hcMembers'),+s.total_members||0);
  animCount($('hcSignals'),+sig.total||0);
  set('hcWinrate',d.performance?.win_rate!=null?Math.round(+d.performance.win_rate)+'%':'—');
  set('hcOnline',fmt(s.online_members));
  animCount($('ssMembers'),+s.total_members||0);
  set('ssOnline',fmt(s.online_members));
  animCount($('ssVip'),+s.vip_members||0);
  animCount($('ssSignals'),+sig.total||0);
  animCount($('ssBuy'),+sig.buy||0);
  animCount($('ssSell'),+sig.sell||0);
  set('ssToday',fmt((+sig.today_free||0)+(+sig.today_vip||0)));
  set('updatedAt','Actualizat '+new Date(d.updated_at||Date.now()).toLocaleTimeString('ro-RO'));
}

function renderSignals(d){
  const inv=d.links?.discord_invite||DISCORD;
  const free=d.signals?.free||[], vip=d.signals?.vip||[];

  const fg=$('freeSignalGrid');
  if(fg) fg.innerHTML=free.length?free.slice(0,6).map(r=>freeCard(r)).join(''):'<div class="sig-empty">🤖 Bot-ul scanează piața… primul semnal FREE apare în curând.</div>';

  const vg=$('vipSignalGrid');
  if(vg){
    if(d.is_admin&&vip.length) vg.innerHTML=vip.slice(0,6).map(r=>adminCard(r)).join('');
    else if(vip.length) vg.innerHTML=vip.slice(0,6).map(r=>lockedCard(r,inv)).join('');
    else vg.innerHTML=[
      {name:'SOL',side:'BUY',status:'live'},{name:'AVAX',side:'BUY',status:'live'},{name:'DOT',side:'SELL',status:'live'}
    ].map(r=>lockedCard(r,inv)).join('');
  }
}

function freeCard(r){
  const buy=r.side==='BUY';
  return `<div class="sig-card">
    <div class="sig-stripe ${buy?'stripe-buy':'stripe-sell'}"></div>
    <div class="sig-top"><span class="sig-coin">${r.name||'—'}</span><span class="sig-badge ${buy?'sig-badge-buy':'sig-badge-sell'}">${r.side}</span></div>
    <div class="sig-row"><span>Entry</span><b>${fmtUsd(r.entry)}</b></div>
    <div class="sig-row"><span>Scor AI</span><b>${r.score??'—'}/100</b></div>
    <div class="sig-row"><span>R:R</span><b>${r.rr?(+r.rr).toFixed(2):'—'}</b></div>
    <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status||'—'}</span></div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)}</div>
  </div>`;
}

function lockedCard(r,inv){
  const buy=r.side==='BUY';
  return `<div class="sig-card sig-locked">
    <div class="sig-stripe stripe-vip"></div>
    <div class="sig-blur">
      <div class="sig-top"><span class="sig-coin">${r.name||'••••'}</span><span class="sig-badge ${buy?'sig-badge-buy':'sig-badge-sell'}">${r.side}</span></div>
      <div class="sig-row"><span>Entry</span><b>$•••••</b></div>
      <div class="sig-row"><span>TP1/TP2/TP3</span><b>•••/•••/•••</b></div>
      <div class="sig-row"><span>Stop Loss</span><b>$•••••</b></div>
      <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status||'live'}</span></div>
    </div>
    <div class="sig-lock-overlay">
      <div class="slo-icon">🔒</div>
      <div class="slo-label">${r.name||'VIP'} ${r.side} — Doar VIP</div>
      <a class="slo-btn" href="${inv}" target="_blank">💎 $25/lună — Deblochează</a>
    </div>
  </div>`;
}

function adminCard(r){
  const buy=r.side==='BUY';
  return `<div class="sig-card" style="border-color:rgba(245,168,0,.3)">
    <div class="sig-stripe stripe-vip"></div>
    <div class="sig-top">
      <span class="sig-coin">${r.name||'—'} <span class="sig-badge sig-badge-vip">VIP</span></span>
      <span class="sig-badge ${buy?'sig-badge-buy':'sig-badge-sell'}">${r.side}</span>
    </div>
    <div class="sig-row"><span>Entry</span><b>${fmtUsd(r.entry)}</b></div>
    <div class="sig-row"><span>Scor AI</span><b>${r.score??'—'}/100</b></div>
    <div class="sig-row"><span>R:R</span><b>${r.rr?(+r.rr).toFixed(2):'—'}</b></div>
    <div class="sig-row"><span>Stop Loss</span><b>${fmtUsd(r.sl)}</b></div>
    <div class="sig-row"><span>Status</span><span class="sig-badge sig-badge-status">${r.status||'—'}</span></div>
    <div class="sig-time">⏱ ${timeAgo(r.sent_at)}</div>
  </div>`;
}

function renderPerformance(d){
  const p=d.performance||{},sig=d.signals||{};
  const wr=+(p.win_rate||0);
  set('perfWR',p.win_rate!=null?Math.round(wr)+'%':'—');
  set('perfClosed',fmt(p.closed));
  set('perfWins',fmt(p.wins));
  set('perfLosses',fmt(p.losses));
  set('perfOpen',fmt(p.open));
  const pnlEl=$('perfAvgPnl');
  if(pnlEl){const v=+(p.avg_pnl_pct||0);pnlEl.textContent=isNaN(v)?'—':(v>=0?'+':'')+v.toFixed(2)+'%';pnlEl.className=v>=0?'pos':'neg';}
  const ring=$('winRing');
  if(ring){
    const deg=Math.max(0,Math.min(100,wr))*3.6;
    const col=wr>=60?'var(--green)':wr>=40?'var(--gold)':'var(--red)';
    ring.style.background=`conic-gradient(${col} ${deg}deg, rgba(255,255,255,0.05) ${deg}deg)`;
  }
  if(p.win_rate!=null) recordPerfHistory(wr);
  renderPerfChart();
  const total=Math.max((+(sig.buy||0))+(+(sig.sell||0)),1);
  const todMax=Math.max((+(sig.today_free||0))+(+(sig.today_vip||0)),1);
  function setBar(bId,lId,val,mx){const b=$(bId);if(b)b.style.width=Math.min(100,Math.round((+val/mx)*100))+'%';set(lId,fmt(val));}
  setBar('aBBuy','aLBuy',sig.buy||0,total);
  setBar('aBSell','aLSell',sig.sell||0,total);
  setBar('aBFree','aLFree',sig.today_free||0,todMax);
  setBar('aBVip','aLVip',sig.today_vip||0,todMax);
}

function renderDiscord(d){
  const s=d.server||{};
  set('dcMembers',fmt(s.total_members));set('dcOnline',fmt(s.online_members));
  set('dcVip',fmt(s.vip_members));set('dcBots',fmt(s.bot_members));
  set('dcText',fmt(s.text_channels));set('dcVoice',fmt(s.voice_channels));set('dcBoosts',fmt(s.boosts));
  const je=$('dcJoins');
  if(je){
    const j=s.recent_joins||[];
    je.innerHTML=j.length?j.map(x=>`<div class="dc-join-item"><span class="dc-join-name">👤 ${x.name}</span><span class="dc-join-ago">${timeAgo(Date.now()/1000-(x.joined_ago||0))}</span></div>`).join(''):'<div class="pt-empty">—</div>';
  }
}

function renderAdmin(d){
  const b=$('adminBanner'); if(!b) return;
  if(d.is_admin){b.classList.remove('hidden');set('adminName',d.admin_user||'admin');}
  else b.classList.add('hidden');
}

// ══════════════════════════════════════════════════════
// PERFORMANCE HISTORY (30-day win-rate trend)
// ══════════════════════════════════════════════════════
const PERF_KEY='rcb_perf_hist_v1';
function loadPerfHist(){ try{return JSON.parse(localStorage.getItem(PERF_KEY))||[];}catch{return [];} }
function savePerfHist(h){ localStorage.setItem(PERF_KEY,JSON.stringify(h)); }

/** Store at most one win-rate sample per calendar day, keep last 30. */
function recordPerfHistory(wr){
  if(isNaN(wr)) return;
  const hist=loadPerfHist();
  const today=new Date().toISOString().slice(0,10);
  const last=hist[hist.length-1];
  if(last&&last.d===today){ last.wr=wr; }
  else { hist.push({d:today,wr:Math.round(wr)}); }
  while(hist.length>30) hist.shift();
  savePerfHist(hist);
}

/** Draw the win-rate trend as an inline SVG line chart in #perfChart. */
function renderPerfChart(){
  const el=$('perfChart'); if(!el) return;
  const hist=loadPerfHist();
  if(hist.length<2){ el.innerHTML='<div class="pt-empty">Graficul apare după câteva zile de date 📈</div>'; return; }
  const pts=hist.map(x=>x.wr);
  const W=520,H=160,pad=24;
  const mn=Math.min(...pts,0),mx=Math.max(...pts,100),rng=(mx-mn)||1;
  const stepX=(W-pad*2)/(pts.length-1);
  const xy=pts.map((p,i)=>[pad+i*stepX,(H-pad)-((p-mn)/rng)*(H-pad*2)]);
  const d=xy.map((c,i)=>`${i?'L':'M'}${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(' ');
  const fill=d+` L${xy[xy.length-1][0].toFixed(1)},${H-pad} L${pad},${H-pad} Z`;
  const lastWr=pts[pts.length-1];
  const col=lastWr>=60?'#00d47e':lastWr>=40?'#f5a800':'#ff2d55';
  const grid=[0,25,50,75,100].map(v=>{const y=(H-pad)-((v-mn)/rng)*(H-pad*2);if(v<mn||v>mx)return '';return `<line x1="${pad}" y1="${y.toFixed(1)}" x2="${W-pad}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,0.05)"/><text x="4" y="${(y+3).toFixed(1)}" font-size="9" fill="var(--muted)">${v}</text>`;}).join('');
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:160px;display:block" preserveAspectRatio="none">
    <defs><linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${col}" stop-opacity=".25"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    ${grid}
    <path d="${fill}" fill="url(#perfGrad)"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${xy[xy.length-1][0].toFixed(1)}" cy="${xy[xy.length-1][1].toFixed(1)}" r="4" fill="${col}"/>
  </svg>`;
}

// ══════════════════════════════════════════════════════
// CANVAS BACKGROUND
// ══════════════════════════════════════════════════════
(function(){
  const c=$('bgCanvas'); if(!c) return;
  const ctx=c.getContext('2d'); let w,h,pts;
  function resize(){
    w=c.width=window.innerWidth; h=c.height=window.innerHeight;
    pts=Array.from({length:Math.min(60,Math.floor(w/22))},()=>({
      x:Math.random()*w,y:Math.random()*h,
      vx:(Math.random()-.5)*.35,vy:(Math.random()-.5)*.35,
      r:Math.random()*1.4+.4,
    }));
  }
  resize(); window.addEventListener('resize',resize,{passive:true});
  (function draw(){
    ctx.clearRect(0,0,w,h);
    for(let i=0;i<pts.length;i++){
      const p=pts[i]; p.x+=p.vx; p.y+=p.vy;
      if(p.x<0||p.x>w)p.vx*=-1; if(p.y<0||p.y>h)p.vy*=-1;
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle='rgba(90,130,255,.4)'; ctx.fill();
      for(let j=i+1;j<pts.length;j++){
        const q=pts[j],dx=p.x-q.x,dy=p.y-q.y,dist=Math.hypot(dx,dy);
        if(dist<110){ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);
          ctx.strokeStyle=`rgba(70,110,220,${.1*(1-dist/110)})`;ctx.lineWidth=1;ctx.stroke();}
      }
    }
    requestAnimationFrame(draw);
  })();
})();

// ══════════════════════════════════════════════════════
// MAIN DATA LOOP
// ══════════════════════════════════════════════════════
async function loadData(){
  try{
    const res=await fetch('/api/stats',{cache:'no-store'});
    if(!res.ok) throw new Error('HTTP '+res.status);
    const d=await res.json();
    _market=d.market||{};

    // If /api/stats returned no prices (bot offline/starting up),
    // inject the direct Binance prices so the UI is never empty.
    if(!(_market.prices&&_market.prices.length) && Object.keys(_DIRECT_PRICES).length) {
      _market = { ...(_market||{}), prices: Object.values(_DIRECT_PRICES) };
    }

    renderStatus(d); renderStats(d); renderTicker(d);
    renderFng(d); renderPrices(d); renderSignals(d);
    renderPerformance(d); renderDiscord(d); renderAdmin(d);
    // notify new signal
    const tot=(d.signals||{}).total;
    if(_prevTotal!==null&&+tot>_prevTotal)
      toast('📡',`Semnal nou!`,'Bot-ul tocmai a trimis un semnal 🔥','toast-buy');
    _prevTotal=+tot||0;
    renderPT();
    // load news once
    if(!_newsLoaded) loadNews();
  }catch(e){
    // /api/stats failed — still render prices from direct Binance fetch.
    if(Object.keys(_DIRECT_PRICES).length){
      _market={prices:Object.values(_DIRECT_PRICES)};
      renderPrices({market:_market}); renderTicker({market:_market});
    }
    set('statusText','Eroare conexiune');
    console.error('panel error',e);
  }
  // Always refresh paper trading panel (uses getPrice which checks all sources)
  renderPT();
  // Update live price in trade form
  const coin=($('ptCoin')||{}).value;
  if(coin) set('tfPrice',fmtUsd(getPrice(coin)));
}

// Wait for direct prices first so the very first loadData() render has fallback data ready.
_fetchDirectPrices().then(loadData);
setInterval(loadData, REFRESH_MS);
setInterval(renderPT, 5000);
