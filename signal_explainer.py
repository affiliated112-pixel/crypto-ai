"""Beginner-friendly signal explainer.
Watches the signal channels and posts a step-by-step trading guide
after each signal the bot sends.

IMPORTANT: We mark our own beginner cards so we don't recurse on them
(otherwise: bot posts signal → we post card → our card triggers on_message
→ we extract BUY from the card → we post another card → INFINITE SPAM).
"""
import re
import discord

SIGNAL_CHANNEL_KEYWORDS = ("signals", "signal", "semnal")
BUY_PATTERNS = re.compile(r"\b(BUY|LONG|CUMPAR|CUMP\u0102R)\b", re.IGNORECASE)
SELL_PATTERNS = re.compile(r"\b(SELL|SHORT|VINDE|V\u00c2NDE)\b", re.IGNORECASE)
SYMBOL_PATTERN = re.compile(r"\b([A-Z]{2,10}USDT?|[A-Z]{2,10}/USDT?|[A-Z]{2,10}-USDT?)\b")
PRICE_PATTERN = re.compile(r"\$?\s*([0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]+)?|[0-9]+\.[0-9]+)")

# Unique marker in our card footer so we can detect our own cards.
BEGINNER_MARKER = "beginner-guide-v1"
# Title prefix of every beginner card.
BEGINNER_TITLE_PREFIX = "👶"
# Skip these embed titles — they're alerts, not trade signals.
NON_SIGNAL_TITLE_HINTS = ("Volume Spike", "High Volatility", "Bot Status", "Status")


def _is_beginner_card(embed):
    """Return True if this embed IS one of our beginner cards."""
    title = embed.title or ""
    if title.startswith(BEGINNER_TITLE_PREFIX):
        return True
    footer = embed.footer.text if embed.footer else ""
    if footer and BEGINNER_MARKER in footer:
        return True
    return False


def _is_signal_embed(embed):
    """Return True if this embed looks like a trade signal (has BUY/SELL + symbol + numeric entry)."""
    title = embed.title or ""
    desc = embed.description or ""
    # Skip alerts and informational embeds
    for hint in NON_SIGNAL_TITLE_HINTS:
        if hint.lower() in title.lower():
            return False
    blob = title + " " + desc
    if not (BUY_PATTERNS.search(blob) or SELL_PATTERNS.search(blob)):
        return False
    if not SYMBOL_PATTERN.search(blob + " " + " ".join(f.value for f in embed.fields)):
        return False
    return True


def _extract_from_embed(embed):
    parts = [(embed.title or ""), (embed.description or "")]
    for f in embed.fields:
        parts.append(f"{f.name} {f.value}")
    blob = " ".join(parts)

    direction = None
    if BUY_PATTERNS.search(blob):
        direction = "BUY"
    elif SELL_PATTERNS.search(blob):
        direction = "SELL"

    sym_match = SYMBOL_PATTERN.search(blob)
    symbol = sym_match.group(1).replace("/", "").replace("-", "") if sym_match else None

    price = None
    # Prefer an Entry field if present (more reliable)
    for f in embed.fields:
        if "entry" in f.name.lower():
            m = PRICE_PATTERN.search(f.value)
            if m:
                try:
                    price = float(m.group(1).replace(",", "").replace(" ", ""))
                    break
                except ValueError:
                    pass
    if price is None:
        m = PRICE_PATTERN.search(blob)
        if m:
            try:
                price = float(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                price = None

    return direction, symbol, price


def _beginner_card(direction, symbol, price):
    coin = symbol.replace("USDT", "").replace("USD", "") if symbol else "COIN"

    if price and price > 0:
        if direction == "BUY":
            sl = price * 0.98
            tp1 = price * 1.02
            tp2 = price * 1.04
            tp3 = price * 1.07
        else:
            sl = price * 1.02
            tp1 = price * 0.98
            tp2 = price * 0.96
            tp3 = price * 0.93
        price_str = f"${price:,.4f}".rstrip("0").rstrip(".")
        sl_str = f"${sl:,.4f}".rstrip("0").rstrip(".")
        tp1_str = f"${tp1:,.4f}".rstrip("0").rstrip(".")
        tp2_str = f"${tp2:,.4f}".rstrip("0").rstrip(".")
        tp3_str = f"${tp3:,.4f}".rstrip("0").rstrip(".")
    else:
        price_str = sl_str = tp1_str = tp2_str = tp3_str = "(check signal above)"

    is_buy = direction == "BUY"
    color = 0x00C896 if is_buy else 0xE74C3C
    emoji = "🟢" if is_buy else "🔴"
    action_ro = "CUMPĂRĂ" if is_buy else "VINDE"
    action_en = "BUY" if is_buy else "SELL"

    embed = discord.Embed(
        title=f"{BEGINNER_TITLE_PREFIX} GHID PENTRU ÎNCEPĂTORI — {emoji} {action_en} {coin}",
        description=(
            f"🇷🇴 *Urmează pașii în ordine. Nu sări peste niciunul.*\n"
            f"🇬🇧 *Follow the steps in order. Don't skip any.*"
        ),
        color=color,
    )

    if is_buy:
        steps = (
            f"**1️⃣** Deschide aplicația **Binance** sau **Bybit**\n"
            f"**2️⃣** Caută perechea **`{coin}/USDT`**\n"
            f"**3️⃣** Apasă pe **`Spot`** (NU `Futures`!)\n"
            f"**4️⃣** Apasă butonul **verde `Buy`**\n"
            f"**5️⃣** Introdu suma — **MAX 5% din portofoliu**\n"
            f"**6️⃣** Apasă **`Buy {coin}`** — ai cumpărat ✅\n"
            f"**7️⃣** **IMEDIAT** pune **Stop Loss** la `{sl_str}`\n"
            f"**8️⃣** Pune **Take Profit** la `{tp1_str}`\n"
        )
    else:
        steps = (
            f"**1️⃣** Dacă **NU ai** {coin} → **ignoră semnalul**\n"
            f"**2️⃣** Dacă **DEȚII DEJA** {coin} → deschide Binance/Bybit\n"
            f"**3️⃣** Caută **`{coin}/USDT`**\n"
            f"**4️⃣** Apasă pe **`Spot`**\n"
            f"**5️⃣** Apasă butonul **roșu `Sell`**\n"
            f"**6️⃣** Vinde **50-70%** din poziție\n"
            f"**7️⃣** Pentru restul, pune **Stop Loss** la `{sl_str}`\n"
        )

    embed.add_field(name=f"📝 Cum să {action_ro.lower()} pas-cu-pas", value=steps, inline=False)
    embed.add_field(
        name="🎯 Prețuri importante",
        value=(
            f"💰 **Entry:** `{price_str}`\n"
            f"🛑 **Stop Loss:** `{sl_str}`\n"
            f"🎯 **TP1:** `{tp1_str}` — *vinde 40%*\n"
            f"🎯 **TP2:** `{tp2_str}` — *vinde 40%*\n"
            f"🎯 **TP3:** `{tp3_str}` — *vinde 20%*"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️ REGULI DE AUR",
        value=(
            "• ❌ NU investi mai mult decât ți-ai permite să pierzi\n"
            "• ❌ NU folosi leverage dacă ești începător\n"
            "• ✅ Întotdeauna pune Stop Loss imediat\n"
            "• ✅ Maxim 5% din portofoliu pe trade"
        ),
        inline=False,
    )
    embed.set_footer(text=f"📚 Educațional • nu sfat financiar • Verifică riscul • {BEGINNER_MARKER}")
    return embed


def install(client):
    """Install on_message + dedup so we never spam our own cards."""
    # Per-message-id guard: never react twice to the same message
    _seen = set()
    MAX_SEEN = 500

    @client.event
    async def on_message(message):
        try:
            if message.author.id != client.user.id:
                return
            if message.id in _seen:
                return
            ch_name = (getattr(message.channel, "name", "") or "").lower()
            if not any(k in ch_name for k in SIGNAL_CHANNEL_KEYWORDS):
                return
            if not message.embeds:
                return

            for emb in message.embeds:
                if _is_beginner_card(emb):
                    # This is our own card — do NOT recurse
                    return
                if not _is_signal_embed(emb):
                    # Not a trade signal (e.g. volume spike alert) — skip
                    continue
                direction, symbol, price = _extract_from_embed(emb)
                if direction and symbol:
                    card = _beginner_card(direction, symbol, price)
                    await message.channel.send(embed=card)
                    _seen.add(message.id)
                    if len(_seen) > MAX_SEEN:
                        # Drop oldest half
                        for _ in range(MAX_SEEN // 2):
                            _seen.pop()
                    return  # one card per message
        except Exception as e:
            print(f"[explainer] on_message error: {e}", flush=True)

    print("[explainer] Installed beginner-friendly signal explainer + fixed on_message handler", flush=True)
