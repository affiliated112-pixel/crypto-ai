"""Beginner-friendly signal explainer.
Watches the signal channels and posts a step-by-step trading guide
after each signal the bot sends. Designed for total beginners.
"""
import re
import discord

SIGNAL_CHANNEL_KEYWORDS = ("signals", "signal", "semnal")
BUY_PATTERNS = re.compile(r"\b(BUY|LONG|CUMPAR|CUMP\u0102R)\b", re.IGNORECASE)
SELL_PATTERNS = re.compile(r"\b(SELL|SHORT|VINDE|V\u00c2NDE)\b", re.IGNORECASE)
SYMBOL_PATTERN = re.compile(r"\b([A-Z]{2,10}USDT?|[A-Z]{2,10}/USDT?|[A-Z]{2,10}-USDT?)\b")
PRICE_PATTERN = re.compile(r"\$?\s*([0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]+)?|[0-9]+\.[0-9]+)")


def _extract_from_embed(embed):
    """Pull direction, symbol, price out of a signal embed."""
    title = (embed.title or "") + " " + (embed.description or "")
    parts = [title]
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
    price_match = PRICE_PATTERN.search(blob)
    if price_match:
        try:
            price = float(price_match.group(1).replace(",", "").replace(" ", ""))
        except ValueError:
            price = None

    return direction, symbol, price


def _beginner_card(direction, symbol, price):
    """Build a step-by-step beginner trading guide as a Discord Embed."""
    coin = symbol.replace("USDT", "").replace("USD", "") if symbol else "COIN"

    # Conservative SL/TP based on signal type (2% SL, 4% TP1)
    if price and price > 0:
        if direction == "BUY":
            sl = price * 0.98
            tp1 = price * 1.02
            tp2 = price * 1.04
            tp3 = price * 1.07
        else:  # SELL / SHORT
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
        title=f"👶 GHID PENTRU ÎNCEPĂTORI — {emoji} {action_en} {coin}",
        description=(
            f"🇷🇴 *Urmează pașii în ordine. Nu sări peste niciunul.*\n"
            f"🇬🇧 *Follow the steps in order. Don't skip any.*"
        ),
        color=color,
    )

    if is_buy:
        steps = (
            f"**1️⃣** Deschide aplicația **Binance** sau **Bybit** (sau cont demo)\n"
            f"**2️⃣** Caută perechea **`{coin}/USDT`**\n"
            f"**3️⃣** Apasă pe **`Spot`** (NU `Futures`! Pentru începători spot e mai sigur)\n"
            f"**4️⃣** Apasă butonul **verde `Buy`**\n"
            f"**5️⃣** Introdu suma — **MAX 5% din portofoliu**\n"
            f"   ⤷️ Dacă ai $1000 → investește max **$50** în acest semnal\n"
            f"**6️⃣** Apasă **`Buy {coin}`** — ai cumpărat ✅\n"
            f"**7️⃣** **IMEDIAT** pune **Stop Loss** la `{sl_str}` (pierdere max ~2%)\n"
            f"**8️⃣** Pune **Take Profit** la `{tp1_str}` (câștig ~2%)\n"
        )
    else:
        steps = (
            f"**1️⃣** Dacă **NU ai** {coin} → **ignoră semnalul** (nu face short ca începător!)\n"
            f"**2️⃣** Dacă **AI** {coin} → deschide Binance/Bybit\n"
            f"**3️⃣** Caută **`{coin}/USDT`**\n"
            f"**4️⃣** Apasă pe **`Spot`**\n"
            f"**5️⃣** Apasă butonul **roșu `Sell`**\n"
            f"**6️⃣** Vinde **50-70%** din poziție (nu tot — lasă ceva pentru cazul în care urcă)\n"
            f"**7️⃣** Pentru restul, pune **Stop Loss** la `{sl_str}`\n"
        )

    embed.add_field(name=f"📝 Cum să {action_ro.lower()} pas-cu-pas", value=steps, inline=False)

    embed.add_field(
        name="🎯 Prețuri importante / Key Prices",
        value=(
            f"💰 **Entry / Intrare:** `{price_str}`\n"
            f"🛑 **Stop Loss:** `{sl_str}` — *aici ieși automat dacă greșim*\n"
            f"🎯 **TP1:** `{tp1_str}` — *vinde 40% aici (în siguranță)*\n"
            f"🎯 **TP2:** `{tp2_str}` — *vinde încă 40%*\n"
            f"🎯 **TP3:** `{tp3_str}` — *vinde ultimii 20% (hold)*"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚠️ REGULI DE AUR / GOLDEN RULES",
        value=(
            "• ❌ **NU** investi mai mult decât ți-ai permite să pierzi\n"
            "• ❌ **NU** folosi **leverage** dacă ești începător\n"
            "• ❌ **NU** cumpăra în **panică** sau **FOMO**\n"
            "• ✅ **Întotdeauna** pune **Stop Loss** imediat după ce intri\n"
            "• ✅ Folosește **maxim 5%** din portofoliu pe un singur trade\n"
            "• ✅ Dacă ești **nesigur** → mai bine sar peste semnal"
        ),
        inline=False,
    )

    embed.set_footer(
        text="📚 Educațional — nu este sfat financiar · DYOR · Folosește /tutorial pentru mai multe"
    )
    return embed


def install(client, original_on_message=None):
    """Install the explainer + a safe on_message that does NOT crash on process_commands.

    Replaces bot.py's broken on_message handler. The original handler calls
    client.process_commands() which doesn't exist on discord.Client (only on Bot),
    so it raised AttributeError on EVERY message. We replace it with a clean
    version that also posts beginner cards under bot signal messages.
    """

    @client.event
    async def on_message(message):
        try:
            # Only act on messages from our bot itself
            if message.author.id != client.user.id:
                return

            # Only in channels that look like signal channels
            ch_name = (getattr(message.channel, "name", "") or "").lower()
            if not any(k in ch_name for k in SIGNAL_CHANNEL_KEYWORDS):
                return

            # Need at least one embed (signal cards are embeds)
            if not message.embeds:
                return

            for emb in message.embeds:
                direction, symbol, price = _extract_from_embed(emb)
                if direction and symbol:
                    card = _beginner_card(direction, symbol, price)
                    await message.channel.send(embed=card)
                    break  # one card per message is enough
        except Exception as e:
            print(f"[explainer] on_message error: {e}", flush=True)

    print("[explainer] Installed beginner-friendly signal explainer + fixed on_message handler", flush=True)
