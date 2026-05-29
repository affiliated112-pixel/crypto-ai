"""
ai_analysis.py — Motor AI unificat pentru semnale crypto.

Modele disponibile (toate gratuite cu tier free):
  1. DeepSeek Chat      — deepseek-chat | 500k tokens/zi gratis | CEL MAI BUN pentru analiză
  2. Groq llama3-70b    — llama-3.3-70b-versatile | ultra-rapid | free tier generos
  3. Google Gemini Flash — gemini-2.0-flash | 15 req/min gratis | foarte capabil
  4. Mistral Small       — mistral-small-latest | 1 req/sec gratis
  5. Cohere Command-R    — command-r | free tier
  6. Fallback local      — fara API, analiza bazata pe indicatori (intotdeauna functioneaza)

Prioritate automata: DeepSeek → Groq → Gemini → Mistral → Cohere → Local

ENV variables:
  DEEPSEEK_API_KEY   — de la https://platform.deepseek.com (gratis $5 credit la signup)
  GROQ_API_KEY       — de la https://console.groq.com (100% gratis, fara card)
  GEMINI_API_KEY     — de la https://aistudio.google.com/app/apikey (gratis)
  MISTRAL_API_KEY    — de la https://console.mistral.ai (free tier)
  COHERE_API_KEY     — de la https://dashboard.cohere.com (free tier)

Utilizare:
  from ai_analysis import ai_analyze
  result = ai_analyze(signal="BUY", symbol="BTCUSDT", price=103000,
                      ind=ind_dict, mtf=mtf_dict)
  # result.text    — analiza principala
  # result.model   — modelul folosit
  # result.en      — text engleza
  # result.ro      — text romana
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

log = logging.getLogger("ai_analysis")

# ─── API KEYS DIN ENV ─────────────────────────────────────────────────────────
DEEPSEEK_KEY  = os.getenv("DEEPSEEK_API_KEY",  "")
GROQ_KEY      = os.getenv("GROQ_API_KEY",      "")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY",    "")
MISTRAL_KEY   = os.getenv("MISTRAL_API_KEY",   "")
COHERE_KEY    = os.getenv("COHERE_API_KEY",    "")

# ─── RATE LIMIT SIMPLU (evita spam la API) ────────────────────────────────────
_last_call:   dict[str, float] = {}
_MIN_INTERVAL = 3.0   # secunde intre apeluri la acelasi provider

def _rate_ok(provider: str) -> bool:
    now = time.time()
    if now - _last_call.get(provider, 0) < _MIN_INTERVAL:
        return False
    _last_call[provider] = now
    return True

# ─── REZULTAT AI ──────────────────────────────────────────────────────────────
@dataclass
class AIResult:
    text:    str = ""          # textul complet (EN + RO)
    en:      str = ""          # doar engleza
    ro:      str = ""          # doar romana
    model:   str = "local"     # modelul care a raspuns
    success: bool = False      # True daca a venit de la un API real

    @property
    def discord_block(self) -> str:
        """Formatted for Discord embed field."""
        if not self.text:
            return ""
        model_badge = f"`{self.model}`"
        return f"🤖 **AI Analysis** — {model_badge}\n{self.text}"

# ─── PROMPT BUILDER ───────────────────────────────────────────────────────────
def _build_prompt(signal: str, symbol: str, price: float,
                  ind: dict, mtf: dict | None) -> str:
    """
    Construieste un prompt detaliat cu toti indicatorii.
    Da AI-ului context real, nu doar RSI si semnal.
    """
    coin = symbol.replace("USDT", "")
    side = "BUY (LONG)" if signal == "BUY" else "SELL (SHORT)"

    rsi      = ind.get("rsi", 50)
    macd_h   = ind.get("macd_hist", 0)
    adx      = ind.get("adx", 20)
    adx_pos  = ind.get("adx_pos", 10)
    adx_neg  = ind.get("adx_neg", 10)
    bb_pct   = ind.get("bb_pct", 0.5)
    bb_width = ind.get("bb_width", 0.03)
    stoch_k  = ind.get("stoch_k", 0.5)
    willr    = ind.get("willr", -50)
    cmf      = ind.get("cmf", 0)
    obv_up   = ind.get("obv_up", False)
    vol_surge = ind.get("vol_surge", False)
    atr      = ind.get("atr", price * 0.02)
    ema9     = ind.get("ema9", price)
    ema20    = ind.get("ema20", price)
    ema50    = ind.get("ema50", price)
    ema200   = ind.get("ema200", price)
    bull_div = ind.get("bull_div", False)
    bear_div = ind.get("bear_div", False)
    struct_bull = ind.get("struct_bull", False)
    struct_bear = ind.get("struct_bear", False)
    struct_score = ind.get("struct_score", 0)
    poc      = ind.get("poc", price)
    fib      = ind.get("fib_levels", {})

    # Volatilitate
    atr_pct  = atr / price * 100 if price > 0 else 2.0
    vol_status = "SURGE (2.5x avg)" if vol_surge else "normal"

    # Trend macro
    macro = "above EMA200 (macro uptrend)" if price > ema200 else "below EMA200 (macro downtrend)"
    ema_stack = "bullish stack (EMA9>EMA20>EMA50)" if (ema9 > ema20 > ema50) else \
                "bearish stack (EMA9<EMA20<EMA50)" if (ema9 < ema20 < ema50) else "mixed EMAs"

    # MTF
    mtf_info = ""
    if mtf:
        aligned = sum(1 for tf in ("5m", "15m", "1h")
                      if mtf.get(tf, {}).get("signal") == signal)
        mtf_info = f"\n  Multi-timeframe: {aligned}/3 timeframes confirm the signal"
        for tf in ("5m", "15m", "1h"):
            sig_tf = mtf.get(tf, {}).get("signal", "NO SIG")
            mtf_info += f"\n    {tf}: {sig_tf}"

    # Fibonacci
    fib_info = ""
    if fib:
        nearest = min(fib.items(), key=lambda x: abs(float(x[1]) - price))
        fib_info = f"\n  Nearest Fibonacci level: {nearest[0]} at ${float(nearest[1]):,.4f}"

    prompt = f"""You are a professional cryptocurrency trader and technical analyst with 10+ years experience.

Analyze this trade signal and provide a concise, professional assessment:

=== TRADE SIGNAL ===
Coin: {coin} (${price:,.4f})
Direction: {side}
Mode: Price is {macro}

=== TECHNICAL INDICATORS ===
Momentum:
  RSI(14): {rsi:.1f} {'[OVERSOLD ⚠️]' if rsi < 30 else '[OVERBOUGHT ⚠️]' if rsi > 70 else '[NEUTRAL]'}
  StochRSI: {stoch_k:.2f} {'[OVERSOLD]' if stoch_k < 0.2 else '[OVERBOUGHT]' if stoch_k > 0.8 else ''}
  Williams %R: {willr:.1f}
  MACD Histogram: {macd_h:+.4f} ({'positive momentum' if macd_h > 0 else 'negative momentum'})

Trend:
  ADX: {adx:.1f} ({'strong trend' if adx > 28 else 'weak/no trend'}) | +DI:{adx_pos:.1f} | -DI:{adx_neg:.1f}
  EMA: {ema_stack}
  EMA9:{ema9:,.2f} | EMA20:{ema20:,.2f} | EMA50:{ema50:,.2f} | EMA200:{ema200:,.2f}
  Market structure: {'HH/HL bullish (score {}/3)'.format(struct_score) if struct_bull else 'LH/LL bearish (score {}/3)'.format(struct_score) if struct_bear else 'no clear structure'}

Volatility & Volume:
  ATR: ${atr:,.4f} ({atr_pct:.2f}% of price)
  Bollinger Band %: {bb_pct:.2f} | BB Width: {bb_width:.3f}
  Volume: {vol_status}
  CMF: {cmf:+.3f} ({'buying pressure' if cmf > 0.1 else 'selling pressure' if cmf < -0.1 else 'neutral'})
  OBV direction: {'UP ✅' if obv_up else 'DOWN'}
  Volume Profile POC: ${poc:,.4f}

Special signals:
  Bullish divergence: {'YES ⚡' if bull_div else 'no'}
  Bearish divergence: {'YES ⚡' if bear_div else 'no'}
{mtf_info}{fib_info}

=== YOUR TASK ===
Write EXACTLY this structure (no more, no less):

🇬🇧 [2-3 sentences in English: explain WHY this signal is valid based on the indicators above. Be specific — mention actual indicator values. End with one sentence about the key risk.]

🇷🇴 [Same analysis translated to Romanian. Use trading terminology correctly.]

Rules:
- Be specific and use the actual numbers from the indicators
- Do NOT use generic phrases like "as with all investments"
- Do NOT add disclaimers or legal warnings
- Focus on the technical picture, not price predictions
- Max 120 words per language"""

    return prompt

# ─── APELURI API ──────────────────────────────────────────────────────────────

def _post_json(url: str, headers: dict, body: dict, timeout: int = 12) -> dict:
    """Generic HTTPS POST cu urllib (fara dependente externe)."""
    data = json.dumps(body).encode("utf-8")
    req  = Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def _deepseek(prompt: str) -> Optional[str]:
    """DeepSeek Chat API — deepseek-chat (gratuit $5 credit la signup)."""
    if not DEEPSEEK_KEY or not _rate_ok("deepseek"):
        return None
    try:
        data = _post_json(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            body={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a professional crypto trader and technical analyst."},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 350,
                "temperature": 0.4,
            }
        )
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.debug(f"[ai] DeepSeek error: {e}")
        return None

def _groq(prompt: str) -> Optional[str]:
    """Groq llama3-70b — cel mai rapid, free tier generos."""
    if not GROQ_KEY or not _rate_ok("groq"):
        return None
    try:
        data = _post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            body={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are a professional crypto trader and technical analyst."},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 350,
                "temperature": 0.4,
            }
        )
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.debug(f"[ai] Groq error: {e}")
        return None

def _gemini(prompt: str) -> Optional[str]:
    """Google Gemini 2.0 Flash — 15 req/min gratis."""
    if not GEMINI_KEY or not _rate_ok("gemini"):
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_KEY}"
        data = _post_json(
            url,
            headers={},
            body={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 350, "temperature": 0.4},
            }
        )
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "").strip() if parts else None
    except Exception as e:
        log.debug(f"[ai] Gemini error: {e}")
        return None

def _mistral(prompt: str) -> Optional[str]:
    """Mistral Small — free tier 1 req/sec."""
    if not MISTRAL_KEY or not _rate_ok("mistral"):
        return None
    try:
        data = _post_json(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_KEY}"},
            body={
                "model": "mistral-small-latest",
                "messages": [
                    {"role": "system", "content": "You are a professional crypto trader."},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 350,
                "temperature": 0.4,
            }
        )
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.debug(f"[ai] Mistral error: {e}")
        return None

def _cohere(prompt: str) -> Optional[str]:
    """Cohere Command-R — free tier."""
    if not COHERE_KEY or not _rate_ok("cohere"):
        return None
    try:
        data = _post_json(
            "https://api.cohere.com/v2/chat",
            headers={"Authorization": f"Bearer {COHERE_KEY}"},
            body={
                "model": "command-r",
                "messages": [
                    {"role": "system", "content": "You are a professional crypto trader."},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 350,
            }
        )
        # Cohere v2 response format
        msg = data.get("message", {})
        content = msg.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "").strip()
        return data.get("text", "").strip() or None
    except Exception as e:
        log.debug(f"[ai] Cohere error: {e}")
        return None

def _local_fallback(signal: str, symbol: str, price: float, ind: dict) -> str:
    """
    Fallback inteligent fara API.
    Construieste o analiza in EN+RO din indicatori direct.
    Nu e AI, dar e bazata pe logica reala — nu text hardcodat generic.
    """
    coin    = symbol.replace("USDT", "")
    rsi     = ind.get("rsi", 50)
    adx     = ind.get("adx", 20)
    macd_h  = ind.get("macd_hist", 0)
    vol_s   = ind.get("vol_surge", False)
    bb_pct  = ind.get("bb_pct", 0.5)
    cmf     = ind.get("cmf", 0)
    ema200  = ind.get("ema200", price)
    struct  = ind.get("struct_bull", False) if signal == "BUY" else ind.get("struct_bear", False)
    bull_d  = ind.get("bull_div", False)
    bear_d  = ind.get("bear_div", False)

    is_buy = signal == "BUY"

    # EN
    parts_en = []
    if is_buy:
        if rsi < 35:
            parts_en.append(f"RSI at {rsi:.1f} signals oversold conditions with high reversal probability.")
        elif rsi < 45:
            parts_en.append(f"RSI at {rsi:.1f} shows bearish exhaustion beginning to ease.")
        if bb_pct < 0.2:
            parts_en.append(f"Price near the lower Bollinger Band ({bb_pct:.2f}) suggests a bounce setup.")
        if adx > 28:
            parts_en.append(f"ADX at {adx:.1f} confirms a strong trending environment favoring bulls.")
        if vol_s:
            parts_en.append("Volume surge detected — institutional participation likely.")
        if bull_d:
            parts_en.append("Bullish RSI divergence adds conviction to the BUY signal.")
        if struct:
            parts_en.append("Market structure shows Higher Highs / Higher Lows — uptrend confirmed.")
        if cmf > 0.1:
            parts_en.append(f"Positive CMF ({cmf:+.2f}) indicates money flow into the asset.")
        if price > ema200:
            parts_en.append(f"Price above EMA200 (${ema200:,.2f}) — macro trend is bullish.")
        parts_en.append(f"Key risk: if price breaks below EMA20 (${ind.get('ema20', price):,.2f}), the setup is invalidated.")
    else:
        if rsi > 65:
            parts_en.append(f"RSI at {rsi:.1f} signals overbought conditions with high rejection probability.")
        elif rsi > 55:
            parts_en.append(f"RSI at {rsi:.1f} shows bullish momentum fading.")
        if bb_pct > 0.8:
            parts_en.append(f"Price near the upper Bollinger Band ({bb_pct:.2f}) suggests a rejection setup.")
        if adx > 28:
            parts_en.append(f"ADX at {adx:.1f} confirms a strong downtrend environment.")
        if vol_s:
            parts_en.append("Volume surge detected on the move down — distribution likely.")
        if bear_d:
            parts_en.append("Bearish RSI divergence adds conviction to the SELL signal.")
        if struct:
            parts_en.append("Market structure shows Lower Highs / Lower Lows — downtrend confirmed.")
        if cmf < -0.1:
            parts_en.append(f"Negative CMF ({cmf:+.2f}) indicates capital outflow from the asset.")
        if price < ema200:
            parts_en.append(f"Price below EMA200 (${ema200:,.2f}) — macro trend is bearish.")
        parts_en.append(f"Key risk: a close above EMA20 (${ind.get('ema20', price):,.2f}) would invalidate the bearish setup.")

    en_text = " ".join(parts_en[:4])   # max 4 propoziții

    # RO (traducere semantica, nu word-by-word)
    parts_ro = []
    if is_buy:
        if rsi < 35:
            parts_ro.append(f"RSI la {rsi:.1f} indică condiții de supravânzare cu probabilitate ridicată de revenire.")
        elif rsi < 45:
            parts_ro.append(f"RSI la {rsi:.1f} arată că presiunea de vânzare începe să scadă.")
        if bb_pct < 0.2:
            parts_ro.append(f"Prețul aproape de banda inferioară Bollinger ({bb_pct:.2f}) sugerează un setup de revenire.")
        if adx > 28:
            parts_ro.append(f"ADX la {adx:.1f} confirmă un trend puternic favorabil pentru cumpărători.")
        if vol_s:
            parts_ro.append("Surge de volum detectat — participare instituțională probabilă.")
        if bull_d:
            parts_ro.append("Divergență bullish RSI adaugă convicție semnalului de BUY.")
        if struct:
            parts_ro.append("Structura pieței arată Higher Highs / Higher Lows — uptrend confirmat.")
        parts_ro.append(f"Risc principal: dacă prețul scade sub EMA20 (${ind.get('ema20', price):,.2f}), setup-ul este invalidat.")
    else:
        if rsi > 65:
            parts_ro.append(f"RSI la {rsi:.1f} indică condiții de supracumpărare cu probabilitate ridicată de corecție.")
        elif rsi > 55:
            parts_ro.append(f"RSI la {rsi:.1f} arată că impulsul bullish se diminuează.")
        if bb_pct > 0.8:
            parts_ro.append(f"Prețul aproape de banda superioară Bollinger ({bb_pct:.2f}) sugerează un setup de respingere.")
        if adx > 28:
            parts_ro.append(f"ADX la {adx:.1f} confirmă un downtrend puternic.")
        if vol_s:
            parts_ro.append("Surge de volum detectat pe mișcarea în jos — distribuție probabilă.")
        if bear_d:
            parts_ro.append("Divergență bearish RSI adaugă convicție semnalului de SELL.")
        if struct:
            parts_ro.append("Structura pieței arată Lower Highs / Lower Lows — downtrend confirmat.")
        parts_ro.append(f"Risc principal: o închidere peste EMA20 (${ind.get('ema20', price):,.2f}) ar invalida setup-ul bearish.")

    ro_text = " ".join(parts_ro[:4])

    return f"🇬🇧 {en_text}\n\n🇷🇴 {ro_text}"

# ─── FUNCTIA PRINCIPALA ───────────────────────────────────────────────────────

def ai_analyze(
    signal:  str,
    symbol:  str,
    price:   float,
    ind:     dict,
    mtf:     dict | None = None,
) -> AIResult:
    """
    Analizeaza un semnal cu AI.
    Incearca in ordine: DeepSeek → Groq → Gemini → Mistral → Cohere → Local.
    Intotdeauna returneaza un rezultat (niciodata nu crapa).

    Args:
        signal:  "BUY" sau "SELL"
        symbol:  ex: "BTCUSDT"
        price:   pretul curent
        ind:     dict de la calc_indicators()
        mtf:     dict cu semnale multi-timeframe (optional)

    Returns:
        AIResult cu .text .en .ro .model .success
    """
    prompt = _build_prompt(signal, symbol, price, ind, mtf)

    # Prioritate: cel mai capabil primul
    providers = [
        ("deepseek-chat",              _deepseek),
        ("llama-3.3-70b (Groq)",       _groq),
        ("gemini-2.0-flash",           _gemini),
        ("mistral-small",              _mistral),
        ("command-r (Cohere)",         _cohere),
    ]

    for model_name, fn in providers:
        try:
            text = fn(prompt)
            if text and len(text) > 50:
                # Separa EN si RO daca ambele sunt in raspuns
                en, ro = _split_en_ro(text)
                log.info(f"[ai] {model_name} → {len(text)} chars")
                return AIResult(text=text, en=en, ro=ro, model=model_name, success=True)
        except Exception as e:
            log.debug(f"[ai] {model_name} failed: {e}")
            continue

    # Fallback local
    text = _local_fallback(signal, symbol, price, ind)
    en, ro = _split_en_ro(text)
    return AIResult(text=text, en=en, ro=ro, model="local", success=False)

def _split_en_ro(text: str) -> tuple[str, str]:
    """Separa textul in portiunea EN si RO dupa flag-urile 🇬🇧/🇷🇴."""
    import re
    en_match = re.search(r"🇬🇧\s*(.*?)(?=🇷🇴|$)", text, re.DOTALL)
    ro_match = re.search(r"🇷🇴\s*(.*?)$", text, re.DOTALL)
    en = en_match.group(1).strip() if en_match else text
    ro = ro_match.group(1).strip() if ro_match else ""
    return en, ro

# ─── COMPATIBILITATE cu bot.py (drop-in replacement) ─────────────────────────

def ai_analysis(signal: str, price: float, rsi: float, symbol: str,
                ind: dict | None = None) -> str:
    """
    Drop-in replacement pentru vechea functie ai_analysis() din bot.py.
    Accepta aceiasi parametri ca inainte + ind optional.
    """
    if ind is None:
        # Construieste un ind minim din ce avem
        ind = {"rsi": rsi, "price": price, "adx": 20, "macd_hist": 0,
               "vol_surge": False, "bb_pct": 0.5, "cmf": 0, "obv_up": True,
               "ema9": price, "ema20": price, "ema50": price, "ema200": price,
               "bull_div": False, "bear_div": False, "struct_bull": False,
               "struct_bear": False, "struct_score": 0, "poc": price,
               "atr": price * 0.02, "fib_levels": {}, "willr": -50,
               "stoch_k": 0.5, "bb_width": 0.03}
    result = ai_analyze(signal=signal, symbol=symbol, price=price, ind=ind)
    return result.text
