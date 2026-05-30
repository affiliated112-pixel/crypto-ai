# Crypto Signals Bot — Railway (ghid complet)

## 1. GitHub

Repo: `affiliated112-pixel/crypto-ai` — branch `main`

Fișiere importante:
- `bot_extended.py` — entrypoint recomandat Railway/Replit (păstrează modulele și pornește extensiile)
- `bot.py` — bot Discord core
- `requirements.txt` — dependențe Python
- `railway.toml` — 1 replică, health check `/health`
- `nixpacks.toml` — suport matplotlib

## 2. Railway — proiect nou sau existent

1. https://railway.app → **New Project** → **Deploy from GitHub**
2. Alege `affiliated112-pixel/crypto-ai`
3. **Settings → Deploy:**
   - Replicas: **1** (obligatoriu)
   - Start Command: `python -u bot_extended.py` (sau lasă `railway.toml`)

## 3. Variables (copy-paste)

**Variables → Raw Editor** — lipește din `railway-variables.txt`:

```env
DISCORD_BOT_TOKEN=tokenul_tau_de_la_discord
```

Fără ghilimele. Token din: Developer Portal → Bot → **Reset Token**.

## 4. Discord Developer Portal

- **Bot** → Intents: **Server Members** + **Message Content**
- **OAuth2** → `bot` + `applications.commands` → invită pe server
- Rol bot: **Send Messages**, **Attach Files**, **Embed Links** în canalele de semnale

## 5. Redeploy

După orice schimbare la Variables → **Deployments → Redeploy**.

## 6. Loguri OK

```text
[config] DISCORD_BOT_TOKEN set (72 chars)
[config] Monitoring: BTCUSDT, ETHUSDT, ...
Bot online: Crypto Signals#4211
[config] #free-signals (FREE_SIGNALS) OK
[SIGNAL LOOP] Done. Next check in 15 min.
```

## 7. Health check

Railway poate folosi: `GET /health` → JSON `{"status":"ok","discord_ready":true}`

Pagina web: URL-ul serviciului Railway (port public).

## 8. Schimbare server Discord

Activează **Developer Mode** în Discord → click dreapta pe canal → **Copy Channel ID** → setează în Railway:

```env
FREE_SIGNALS_CHANNEL=1234567890123456789
VIP_SIGNALS_CHANNEL=...
```

## 9. Probleme frecvente

| Eroare | Soluție |
|--------|---------|
| `401` / `LoginFailure` | Token greșit sau 2 replici — Replicas=1, token nou |
| `session invalidated` | Două containere simultan — așteaptă deploy vechi să moară |
| Nu postează în canal | Verifică ID canal + permisiuni bot |
| `matplotlib` missing | `requirements.txt` pe GitHub + redeploy |


## 10. Note real-data

- Botul folosește `market_data.py`: Binance Global → Binance.US → CoinGecko fallback.
- `/stats`, `/history` și performance-ul zilnic citesc din tracker-ul real TP/SL, nu din procente inventate.
- `bot_extended.py` este recomandat pentru că păstrează modulele extra, dar nu dublează loop-urile de semnale.
- Extra modulele demo/paper/auto-trade pornesc doar dacă setezi explicit `DEMO_APP_ENABLED=1`, `PAPER_TRADING_ENABLED=1` sau `AUTO_TRADE_ENABLED=1`.
