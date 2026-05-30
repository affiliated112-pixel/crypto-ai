# Crypto Discord Signals Bot

A Discord bot that monitors BTC/USDT on Binance, calculates RSI signals, and posts free and VIP trading signals to designated Discord channels.

## Features
- RSI-based BUY/SELL signal generation (5-minute candles)
- Free signals channel and VIP signals with TP/SL targets
- Welcome messages for new members
- Periodic market news and announcement messages
- Bilingual support (English / Romanian)

## Setup

### Required Secret
- `DISCORD_BOT_TOKEN` — Your Discord bot token from the Discord Developer Portal

### Run
```
python bot.py
```

## User Preferences
- Token stored as a secret (never hardcoded)
