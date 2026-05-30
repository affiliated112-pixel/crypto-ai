# Crypto Signals Bot — Railway setup

## 1. Deploy

Railway → **New Project** → Deploy from GitHub/upload.

Start command:

```bash
python -u bot_extended.py
```

Setează **Replicas = 1**. Este important pentru cooldown, dedupe și Discord session.

## 2. PostgreSQL

Recomandat: adaugă un serviciu **PostgreSQL** în același proiect Railway.

Railway va pune automat `DATABASE_URL` în service variables. Botul detectează `DATABASE_URL` și creează tabelele singur.

Dacă nu există `DATABASE_URL`, botul folosește SQLite fallback, dar pentru production folosește PostgreSQL.

## 3. Variables

Railway → Service → **Variables → Raw Editor** → lipește din `railway-variables.txt`.

Obligatoriu:

```env
DISCORD_BOT_TOKEN=tokenul_tau_de_la_discord
USE_PERSISTENT_STATE=1
SIGNAL_MODE=balanced
```

## 4. Unde pui ID-urile canalelor Discord

Tot în Railway Variables:

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

Cum iei ID-ul: Discord → User Settings → Advanced → **Developer Mode ON** → click dreapta pe canal → **Copy Channel ID**.

## 5. Discord permissions

În Discord, rolul botului trebuie să aibă pe canalele relevante:

```text
Send Messages
Embed Links
Attach Files
Read Message History
Use Slash Commands
```

## 6. Comenzi de verificare după deploy

În Discord:

```text
/admin_channels
/admin_status
/admin_last_blocked
/admin_why BTC
```

`/admin_channels` îți arată dacă ID-urile sunt bune și dacă botul are permisiuni.

## 7. Health check

Railway health endpoint:

```text
/health
/healthz
```

`/health` include DB backend, budget, last scan, last signal, queue size și erori recente.

## 8. Backtesting praguri

După ce instalezi requirements:

```bash
python backtest_thresholds.py --tier free --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 5m --limit 1000
python backtest_thresholds.py --tier vip --interval 5m --limit 1000 --output backtest_results.csv
```

## 9. Probleme frecvente

| Problemă | Soluție |
|---|---|
| `401` / `LoginFailure` | Token greșit; regenerează tokenul Discord |
| `session invalidated` | Replicas trebuie să fie 1 |
| Nu postează în canal | Verifică variabila `*_CHANNEL` și rulează `/admin_channels` |
| Chart nu se trimite | Verifică `Attach Files`; botul va trimite fallback fără chart |
| Semnale blocate | Rulează `/admin_last_blocked` sau `/admin_why BTC` |
| După restart trimite duplicate | Verifică `DATABASE_URL` și `USE_PERSISTENT_STATE=1` |
