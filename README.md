# Crypto AI Discord Bot

Discord bot pentru crypto signals, alerts, paper/demo trading, educație, news și sentiment analysis.

Varianta asta rulează în **real-data mode**: prețurile vin din Binance Global/US cu fallback CoinGecko, news/sentiment vin din surse publice, iar performance-ul se calculează doar din semnalele urmărite în tracker. Nu sunt inventate win-rate-uri, PnL-uri, prețuri sau rezultate.

## Setup

```bash
python -m pip install -r requirements.txt
```

Setează tokenul Discord în environment variables:

```bash
DISCORD_BOT_TOKEN=tokenul_tau
```

Run recomandat:

```bash
python -u bot_extended.py
```

`bot.py` rămâne modulul principal. `bot_extended.py` este entrypoint-ul sigur pentru Railway/Replit și pornește extra modulele doar când le activezi explicit.

## Config opțional

Poți folosi `config.json` pentru channel IDs și lista de simboluri, fără să modifici codul:

```json
{
  "FREE_SIGNALS_CHANNEL": 1509522466106642442,
  "VIP_SIGNALS_CHANNEL": 1509522877966319848,
  "ALERTS_CHANNEL": 1509524631332196422,
  "STATUS_CHANNEL": 1509524579364638830,
  "SYMBOLS": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
}
```

## Extra module

Activează doar ce vrei să ruleze:

```bash
DEMO_APP_ENABLED=1
PAPER_TRADING_ENABLED=1
AUTO_TRADE_ENABLED=1
```

Auto-trader-ul este manual by default. Pe LIVE, `AUTO_TRADE_AUTO=true` este ignorat dacă nu setezi explicit:

```bash
AUTO_TRADE_ALLOW_LIVE_AUTO=true
```

Lasă-l pe manual/testnet până verifici totul în Discord.

## Features reale

- Slash commands pentru market data, semnale, scan, help, stats, admin, paper/demo și auto-trader.
- Market data centralizat în `market_data.py`: Binance Global → Binance.US → CoinGecko fallback.
- Quality gate înainte de semnale automate: scor, R:R, BTC macro context, cooldown, correlation și daily limits.
- TP/SL din ATR, folosite la fel în embed-uri, tracker și rezultate.
- Performance stats din `tracker.py` / `signal_results.py`, nu din valori hardcodate.
- AI analysis doar dacă ai API key valid; fallback-ul local folosește indicatorii calculați.
- Health endpoint Railway: `/health` și `/healthz`.

## Verificare

```bash
python -m py_compile *.py
```

Am păstrat lista de coin-uri și modulele existente; modificările sunt pentru stabilitate, date reale, comandă/sync mai corect și wording mai honest.

## Disclaimer

Semnalele sunt educaționale, nu sfat financiar. Rezultatele trecute nu garantează rezultate viitoare.
