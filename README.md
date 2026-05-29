# Crypto AI Bot

This repo contains a Discord bot for crypto signals, trading simulations, and analysis.

Quick start:

```bash
python -m pip install -r requirements.txt
# set DISCORD_BOT_TOKEN or DISCORD_TOKEN in env
python bot.py
```

Train model (optional):

```bash
python train_model.py
```

Deploy with Docker (example):

```bash
docker build -t crypto-ai .
docker run -e DISCORD_BOT_TOKEN="$TOKEN" crypto-ai
```
