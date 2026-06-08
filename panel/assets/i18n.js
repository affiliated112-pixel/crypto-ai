'use strict';
/* ══════════════════════════════════════════════════════
   Romania Crypto Signals — lightweight i18n (RO / EN)
   Translates any element carrying a data-i18n="key" attribute.
   ══════════════════════════════════════════════════════ */

const I18N = {
  ro: {
    nav_market: '📊 Piață', nav_chart: '📈 Chart', nav_signals: '📡 Semnale',
    nav_trading: '🎮 Trading', nav_news: '📰 News', nav_track: '🏆 Track',
    hero_desc: 'Bot AI care scanează 30+ monede 24/7 cu RSI, MACD, Bollinger Bands. Entry exact, TP și SL calculat automat. Trimis pe Discord înainte să ratezi mișcarea.',
    cta_discord: 'Discord Gratuit', cta_chart: '📈 Chart Live', cta_demo: '🎮 Demo Trading',
    lbl_members: 'Membri', lbl_signals: 'Semnale', lbl_winrate: 'Win Rate', lbl_online: 'Online acum',
    market_title: 'Piața', market_sub: 'Prețuri actualizate live · Fear & Greed · Sparklines 24h',
    alerts_title: '🔔 Alerte de preț', alerts_sub: 'Primește o notificare în browser când prețul atinge ținta ta.',
    alerts_empty: 'Nicio alertă activă. Adaugă una mai sus 👆',
    alerts_add: '➕ Adaugă alertă', alerts_coin: 'Monedă', alerts_when: 'Condiție', alerts_target: 'Preț țintă ($)',
    above: '▲ Peste', below: '▼ Sub',
    news_title: '📰 Crypto News', news_refresh: '🔄 Actualizează',
    track_title: '🏆 Track Record', perf_chart_title: '📈 Evoluție Win Rate (30 zile)',
  },
  en: {
    nav_market: '📊 Market', nav_chart: '📈 Chart', nav_signals: '📡 Signals',
    nav_trading: '🎮 Trading', nav_news: '📰 News', nav_track: '🏆 Track',
    hero_desc: 'AI bot scanning 30+ coins 24/7 with RSI, MACD, Bollinger Bands. Exact entry, auto-calculated TP & SL. Sent on Discord before you miss the move.',
    cta_discord: 'Free Discord', cta_chart: '📈 Live Chart', cta_demo: '🎮 Demo Trading',
    lbl_members: 'Members', lbl_signals: 'Signals', lbl_winrate: 'Win Rate', lbl_online: 'Online now',
    market_title: 'Market', market_sub: 'Live prices · Fear & Greed · 24h sparklines',
    alerts_title: '🔔 Price alerts', alerts_sub: 'Get a browser notification when price hits your target.',
    alerts_empty: 'No active alerts. Add one above 👆',
    alerts_add: '➕ Add alert', alerts_coin: 'Coin', alerts_when: 'Condition', alerts_target: 'Target price ($)',
    above: '▲ Above', below: '▼ Below',
    news_title: '📰 Crypto News', news_refresh: '🔄 Refresh',
    track_title: '🏆 Track Record', perf_chart_title: '📈 Win Rate trend (30 days)',
  },
};

let _lang = localStorage.getItem('rcb_lang') || 'ro';

/** Translate a single key in the active language (falls back to RO, then the key). */
function t(key) {
  return (I18N[_lang] && I18N[_lang][key]) || I18N.ro[key] || key;
}

/** Apply translations to every [data-i18n] element on the page. */
function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const val = t(key);
    if (val) el.textContent = val;
  });
  document.documentElement.setAttribute('lang', _lang);
  const btn = document.getElementById('langToggle');
  if (btn) btn.textContent = _lang === 'ro' ? '🇷🇴 RO' : '🇬🇧 EN';
}

/** Toggle RO ↔ EN and persist the choice. */
function toggleLang() {
  _lang = _lang === 'ro' ? 'en' : 'ro';
  localStorage.setItem('rcb_lang', _lang);
  applyI18n();
}

document.addEventListener('DOMContentLoaded', applyI18n);
