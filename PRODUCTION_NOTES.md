# Production notes

## Ce s-a adăugat pentru stabilitate

1. **Persistent DB** în `db.py`
   - PostgreSQL dacă există `DATABASE_URL`.
   - SQLite fallback pentru local/test.
   - Tabele pentru semnale, blocked signals, Discord attempts, daily counters, runtime state și signal results.

2. **Dedupe / idempotency**
   - Fiecare semnal are `signal_id` stabil.
   - Dacă Railway restartează botul, același semnal nu se retrimite inutil.

3. **Discord send queue** în `reliable_send.py`
   - Retry cu backoff.
   - Respectă `retry_after` dacă Discord rate-limitează.
   - Fallback embed-only dacă chart upload eșuează.

4. **Admin diagnostics** în `commands_reliability.py`
   - `/admin_status`
   - `/admin_last_blocked`
   - `/admin_recent_sent`
   - `/admin_why`
   - `/admin_channels`

5. **Health endpoint real**
   - `/health` include Discord ready, loop state, scan timestamps, DB summary, queue size și budget.

6. **Tracker rezultate** în `tracker.py`
   - Fees.
   - Slippage.
   - TP1/TP2/TP3 parțial.
   - Break-even după TP1.
   - Expirare semnal.

7. **Backtesting** în `backtest_thresholds.py`
   - Testează praguri de scor/R:R pe candles istorice.
   - Scrie CSV cu win rate, avg PnL, TP/SL rates.

## Mesaje Discord

Am schimbat wording-ul public către mesaje mai serioase:

- `Technical Rationale`
- `Trade Rationale`
- `Market data`
- `Manage risk`

Fără texte publice de tip marketing sau formulări neserioase, etc.
