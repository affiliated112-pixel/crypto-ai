# Crypto AI Bot

Discord bot for crypto signals, alerts, paper trading, and sentiment analysis.

## Setup

```bash
python -m pip install -r requirements.txt
```

Set your bot token in environment variables:

- `DISCORD_BOT_TOKEN`
- or `DISCORD_TOKEN`

Then run:

```bash
python bot.py
```

## Optional config

A local `config.json` can override channel IDs and symbol list if you prefer not to use env vars.

Example `config.json`:

```json
{
  "FREE_SIGNALS_CHANNEL": 1509522466106642442,
  "VIP_SIGNALS_CHANNEL": 1509522877966319848,
  "ALERTS_CHANNEL": 1509524631332196422,
  "STATUS_CHANNEL": 1509524579364638830,
  "SYMBOLS": ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT"]
}
```

## Features

- Discord slash commands for crypto signals and trading education
- SQLite persistence for alerts, signal history, and portfolios
- AI-backed signal explanation support using Groq, Cohere, OpenRouter, or HuggingFace
- Docker support and GitHub Actions CI
- Training script for a simple signal classifier

## Train the model

```bash
python train_model.py
```

This script reads saved signals from `bot_data.db` and stores a model at `model.joblib`.

## Docker

```bash
docker build -t crypto-ai .
docker run -e DISCORD_BOT_TOKEN="$TOKEN" crypto-ai
```

## CI

The workflow at `.github/workflows/ci.yml` installs dependencies and runs `python -m py_compile`.
