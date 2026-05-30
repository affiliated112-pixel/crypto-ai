# Crypto Discord Signals Bot

Discord bot pentru crypto signals, alerts, market news, performance tracking și comenzi admin.

Varianta asta rulează în **real-data mode**: prețurile vin din Binance Global/US cu fallback CoinGecko, news/sentiment vin din surse publice, iar performance-ul se calculează doar din semnalele urmărite în tracker. Mesajele publice sunt păstrate serioase: tehnic, scurt, fără texte de marketing.

## Setup local

```bash
python -m pip install -r requirements.txt
python -u bot_extended.py
```

Pentru Railway, folosește `railway-variables.txt` ca template pentru Variables.

## Unde pui ID-urile canalelor Discord

În Railway: **Project → Service → Variables → Raw Editor**.

Variabilele principale:

```env
FREE_SIGNALS_CHANNEL=ID_CANAL_FREE
VIP_SIGNALS_CHANNEL=ID_CANAL_VIP
STATUS_CHANNEL=ID_CANAL_STATUS
ALERTS_CHANNEL=ID_CANAL_ALERTS
PERFORMANCE_CHANNEL=ID_CANAL_PERFORMANCE
MARKET_NEWS_CHANNEL=ID_CANAL_NEWS
WELCOME_CHANNEL=ID_CANAL_WELCOME
RULES_CHANNEL=ID_CANAL_RULES
HOWTO_CHANNEL=ID_CANAL_HOWTO
GET_VIP_CHANNEL=ID_CANAL_GET_VIP
ANNOUNCEMENTS_CHANNEL=ID_CANAL_ANNOUNCEMENTS
```

Cum iei un ID: Discord → **User Settings → Advanced → Developer Mode ON** → click dreapta pe canal → **Copy Channel ID**.

După deploy, rulează în Discord:

```text
/admin_channels
/admin_status
```

## PostgreSQL / persistent DB

Recomandat pe Railway: adaugă serviciul **PostgreSQL** în același proiect. Railway va injecta automat `DATABASE_URL`. Botul creează singur tabelele la pornire.

Dacă `DATABASE_URL` nu există, botul folosește SQLite fallback. Pentru production, PostgreSQL este recomandat.

## Reliability features

- Persistent DB pentru semnale trimise, semnale blocate, cooldown, daily budget, status runtime și tracking rezultate.
- `signal_id` unic + dedupe ca să nu trimită același semnal după restart/redeploy.
- Discord send queue cu retry și fallback fără chart dacă upload-ul de chart pică.
- Health endpoint mai complet: `/health` și `/healthz`.
- Admin slash commands: `/admin_status`, `/admin_last_blocked`, `/admin_recent_sent`, `/admin_why`, `/admin_channels`.
- Tracker de rezultate cu fees, slippage, TP parțial, break-even după TP1 și expirare.
- Backtesting thresholds: `backtest_thresholds.py`.

## Backtesting

Exemple:

```bash
python backtest_thresholds.py --tier free --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 5m --limit 1000
python backtest_thresholds.py --tier vip --interval 5m --limit 1000 --output backtest_results.csv
```

Scriptul testează praguri de scor și R:R, simulează TP1/TP2/TP3 parțial, fee/slippage și scrie rezultatele în CSV.

## Config semnale

```env
SIGNAL_MODE=balanced
FREE_MIN_SCORE=42
VIP_MIN_SCORE=52
FREE_MIN_RR=1.6
VIP_MIN_RR=1.8
FREE_COOLDOWN_H=6
VIP_COOLDOWN_H=4
FREE_MAX_PER_DAY=5
VIP_MAX_PER_DAY=10
```

`SIGNAL_MODE=balanced` este recomandat. `strict` trimite mai rar, `aggressive` trimite mai des.

## Railway checklist

```text
Replicas = 1
DISCORD_BOT_TOKEN setat
DATABASE_URL prezent dacă folosești PostgreSQL
Channel IDs setate în Variables
Bot permissions: Send Messages, Embed Links, Attach Files
```

## Disclaimer

Semnalele sunt educaționale, nu sfat financiar. Rezultatele trecute nu garantează rezultate viitoare.
