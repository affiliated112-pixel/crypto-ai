# Deploy pe Railway (copy-paste)

## 1. GitHub — `requirements.txt`

Asigură-te că pe repo ai:

```txt
discord.py
requests
pandas
ta
matplotlib
```

## 2. Railway — variabile de mediu

**Project → serviciul botului → Variables → Raw Editor**

Lipește (înlocuiește `PUNE_TOKENUL_AICI`):

```env
DISCORD_BOT_TOKEN=PUNE_TOKENUL_AICI
```

Opțional (AI):

```env
GROQ_API_KEY=
COHERE_API_KEY=
OPENROUTER_API_KEY=
```

**Important:** fără ghilimele, fără `Bot ` în fața tokenului.

## 3. Discord Developer Portal

1. https://discord.com/developers/applications → aplicația ta → **Bot**
2. **Reset Token** → copiază → lipește în `DISCORD_BOT_TOKEN` pe Railway
3. **Privileged Gateway Intents** — activează:
   - Server Members Intent
   - Message Content Intent
4. **OAuth2 → URL Generator** — bifează `bot` + `applications.commands` → generează link → invită botul pe server

## 4. Railway — deploy

- **Settings → Source:** repo `affiliated112-pixel/crypto-ai` (branch `main`)
- **Settings → Deploy:** Start Command = `python bot.py` (sau lasă `railway.toml`)
- După Variables → **Deploy** / **Redeploy**

## 5. Loguri OK

```text
Keep-alive server running on port ...
Bot online: NumeleBot#1234
Slash commands synced.
```

Dacă vezi mesajul `DISCORD TOKEN LIPSESTE` → variabila nu e setată sau serviciul nu a fost redeploy-at.

## 6. Canale Discord

ID-urile de canal din `bot.py` sunt pentru serverul tău. Dacă folosești alt server, actualizează liniile `WELCOME_CHANNEL`, `FREE_SIGNALS_CHANNEL`, etc. (click dreapta pe canal → Copy Channel ID, cu Developer Mode activat în Discord).
