# Romania Crypto Signals — Web Panel

A serious, real-time web panel served by the **same** bot process (no extra service, no extra Railway deploy).

## How it works

The bot already runs an HTTP keep-alive/health server on Railway's `PORT`. That same
server now also serves the panel:

| Route          | What it returns                                              |
| -------------- | ----------------------------------------------------------- |
| `/`            | The panel website (`panel/index.html`)                      |
| `/assets/*`    | Static CSS / JS / logo (`panel/assets/`)                    |
| `/api/stats`   | Live JSON with real data from Discord + the bot database    |
| `/health`      | Existing health JSON (unchanged)                            |

The front-end (`panel/assets/app.js`) polls `/api/stats` every 15s and renders:

- **Members** — real `guild.member_count` from Discord
- **Online members** — requires the `PRESENCE_INTENT` flag (see below)
- **VIP members** — counted by the `VIP_ROLE_NAME` role
- **Signals** — BUY / SELL / total live counters
- **Performance (30d)** — win rate, wins/losses, avg PnL from the tracker DB
- **Recent signals** — last signals sent, from the `signals_sent` table

All data is read-only and defensive — the panel can never crash the bot.

## Files

```
panel/
├── index.html          # the website
├── assets/
│   ├── styles.css      # dark RCB theme (blue/yellow/red)
│   ├── app.js          # fetches /api/stats and renders
│   └── rcb-logo.png    # logo
└── README.md
panel_data.py           # collects live stats from client + db
```

## Online members (optional, privileged intent)

`member_count`, `vip_members` and signal stats work out of the box.

To show **online members** you must enable the privileged **Presence Intent**:

1. Discord Developer Portal → your app → **Bot** → enable **Presence Intent**.
2. In Railway add the variable: `PRESENCE_INTENT=1`.

Without it the panel still works — the "Online" card just stays at 0.

## Local test

```bash
python -u bot_extended.py
# then open http://localhost:8080/
```

## Railway

Nothing extra to configure — it deploys with the bot. After deploy, open your
Railway public URL (the same one used for `/health`) and you'll see the panel.
