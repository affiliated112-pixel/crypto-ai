# Real-data / no-fake cleanup

This patch keeps the existing Discord bot structure and modules, but tightens the project so it avoids invented numbers, duplicate registrations, and weak automatic signals.

## What changed

- Added/kept a central `market_data.py` helper for live public market data:
  - Binance Global first
  - Binance.US fallback
  - CoinGecko fallback when exchange candles are unavailable
- Updated `bot.py` data calls to use real OHLCV/price helpers instead of generated or hardcoded market values.
- Added a real signal quality gate before automatic Discord signal sends:
  - score threshold
  - risk/reward check
  - BTC macro context
  - active-hours filter
  - daily signal budget
  - cooldown/correlation checks
- Updated TP/SL tracking to use the same ATR-based levels that users see in Discord.
- Reworked `commands_ext.py` and `commands_ext2.py` so optional slash commands do not overwrite existing commands unless explicitly requested.
- Added transparent news/sentiment behavior:
  - public RSS / CoinGecko news
  - public Reddit JSON only when available
  - no invented Reddit counts, win rates, or AI-generated fake summaries
- Updated signal embeds to safer, more honest wording:
  - “setup” instead of guaranteed entry
  - educational disclaimer
  - 1–2% risk language
  - no guaranteed profit or fake probability claims
- Updated `bot_extended.py` into a safe wrapper:
  - no duplicate signal loops
  - optional demo/paper/auto-trade extras via env flags
  - keeps modules available without forcing extra loops

## Optional env flags

Use these only when you want the extra modules running:

```bash
DEMO_APP_ENABLED=1
PAPER_TRADING_ENABLED=1
AUTO_TRADE_ENABLED=1
```

Admin owners can be configured with:

```bash
OWNER_IDS=123456789,987654321
```

## Verification performed

```bash
python -m compileall -q .
```

The code compiles syntactically across all Python modules. A full live Discord run still requires installing `requirements.txt` and setting a valid `DISCORD_BOT_TOKEN` in the deployment environment.
