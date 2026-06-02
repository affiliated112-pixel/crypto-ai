"""Premium Discord embeds for the RCB community channels.

This module keeps the visual community messages separate from the trading
logic. It uses the local logo asset when the bot has Attach Files permission
and falls back gracefully to text-only branding when attachments are blocked.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

import discord

BRAND_NAME = os.environ.get("BRAND_NAME", "RCB Crypto AI")
BRAND_TAGLINE = os.environ.get(
    "BRAND_TAGLINE",
    "AI crypto signals • live market data • risk-first trading",
)
LOGO_FILENAME = "rcb-logo.png"
LOGO_PATH = Path(__file__).with_name("assets") / LOGO_FILENAME
LOGO_ATTACHMENT_URL = f"attachment://{LOGO_FILENAME}"
OPTIONAL_LOGO_URL = os.environ.get("RCB_LOGO_URL", "").strip()

BRAND_BLUE = 0x0A84FF
BRAND_YELLOW = 0xFFD60A
BRAND_RED = 0xFF3B30
BRAND_GREEN = 0x30D158
BRAND_PURPLE = 0x8B5CF6
BRAND_DARK = 0x111827
BRAND_GREY = 0x94A3B8

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
MINI_DIVIDER = "╼━━━━━━━━━━━━━━━━━━━━╾"

SOURCE_REPUTATION = {
    "coindesk": "established crypto newsroom",
    "the block": "research + institutional crypto coverage",
    "decrypt": "independent crypto newsroom",
    "cointelegraph": "major crypto newsroom",
    "bitcoin magazine": "Bitcoin-focused specialist outlet",
    "cryptoslate": "crypto market + sector coverage",
    "coingecko": "market data/news aggregator",
}


def _can_attach_files(channel: discord.abc.Messageable) -> bool:
    if isinstance(channel, discord.TextChannel):
        me = channel.guild.me
        if me is None:
            return False
        return bool(channel.permissions_for(me).attach_files)
    return True


def _logo_file(channel: discord.abc.Messageable) -> discord.File | None:
    if LOGO_PATH.is_file() and _can_attach_files(channel):
        return discord.File(str(LOGO_PATH), filename=LOGO_FILENAME)
    return None


def _logo_url(channel: discord.abc.Messageable) -> str:
    if LOGO_PATH.is_file() and _can_attach_files(channel):
        return LOGO_ATTACHMENT_URL
    return OPTIONAL_LOGO_URL


def _safe_field_value(text: str, limit: int = 1024) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text or "—"
    return text[: max(0, limit - 1)].rstrip() + "…"


def _source_reputation(source: str) -> str:
    key = (source or "").strip().lower()
    return SOURCE_REPUTATION.get(key, "public crypto news feed")


def _branded_embed(
    embed: discord.Embed,
    channel: discord.abc.Messageable,
    *,
    author_name: str | None = None,
    thumbnail: bool = True,
    keep_thumbnail: bool = True,
) -> discord.Embed:
    """Apply RCB branding without breaking if the logo cannot be attached."""
    logo = _logo_url(channel)
    current_author = getattr(embed, "author", None)
    current_author_name = getattr(current_author, "name", None) or ""
    author_text = author_name or current_author_name or BRAND_NAME

    if logo:
        embed.set_author(name=author_text, icon_url=logo)
        if thumbnail and (not keep_thumbnail or not getattr(embed.thumbnail, "url", None)):
            embed.set_thumbnail(url=logo)
    else:
        embed.set_author(name=author_text)
    return embed


async def send_branded(
    channel: discord.abc.Messageable,
    embed: discord.Embed,
    *,
    author_name: str | None = None,
    content: str | None = None,
    thumbnail: bool = True,
    keep_thumbnail: bool = True,
) -> None:
    """Send one branded embed with graceful fallback when attachments fail."""
    _branded_embed(
        embed,
        channel,
        author_name=author_name,
        thumbnail=thumbnail,
        keep_thumbnail=keep_thumbnail,
    )
    logo_file = _logo_file(channel)
    try:
        if logo_file:
            await channel.send(content=content, embed=embed, file=logo_file)
        else:
            await channel.send(content=content, embed=embed)
    except discord.Forbidden:
        # Fallback for channels where Attach Files is blocked after permission check.
        embed.set_author(name=author_name or BRAND_NAME)
        if getattr(embed.thumbnail, "url", None) == LOGO_ATTACHMENT_URL:
            embed.set_thumbnail(url=None)
        await channel.send(content=content, embed=embed)


async def send_branded_once(
    channel: discord.abc.Messageable | None,
    embeds: discord.Embed | Iterable[discord.Embed],
    keyword: str,
    *,
    content: str | None = None,
    history_limit: int = 50,
) -> bool:
    """Post setup embeds only once, using the title keyword for dedupe."""
    if channel is None:
        return False
    keyword_l = keyword.lower().strip()
    try:
        async for msg in channel.history(limit=history_limit):
            if msg.author.bot and msg.embeds:
                for old in msg.embeds:
                    title = (old.title or "").lower()
                    desc = (old.description or "").lower()
                    if keyword_l and (keyword_l in title or keyword_l in desc):
                        return False
    except Exception:
        # If history is unavailable, it is better to post than silently fail.
        pass

    embed_list = [embeds] if isinstance(embeds, discord.Embed) else list(embeds)
    logo_file = _logo_file(channel)
    for embed in embed_list:
        _branded_embed(embed, channel)
    try:
        if logo_file:
            await channel.send(content=content, embeds=embed_list, file=logo_file)
        else:
            await channel.send(content=content, embeds=embed_list)
    except discord.Forbidden:
        for embed in embed_list:
            embed.set_author(name=BRAND_NAME)
            if getattr(embed.thumbnail, "url", None) == LOGO_ATTACHMENT_URL:
                embed.set_thumbnail(url=None)
        await channel.send(content=content, embeds=embed_list)
    return True


def build_welcome_board(channel_ids: dict[str, int], guild_name: str | None = None) -> discord.Embed:
    guild_label = guild_name or "RCB Community"
    embed = discord.Embed(
        title="🚀 RCB Welcome Hub / Bun venit în comunitate",
        description=(
            f"**{guild_label}** is your AI-powered crypto workspace: signals, market news, "
            "education and risk-first trading flow.\n\n"
            f"{DIVIDER}\n"
            "🇷🇴 Intră, citește regulile, verifică FAQ-ul și folosește semnalele cu disciplină.\n"
            "🇬🇧 Join in, read the rules, check the FAQ and use signals with discipline."
        ),
        color=BRAND_BLUE,
    )
    embed.add_field(
        name="🧭 Start aici / Start here",
        value=(
            f"📜 Rules / Reguli → <#{channel_ids['rules']}>\n"
            f"❓ FAQ / Întrebări → <#{channel_ids['faq']}>\n"
            f"📊 How-to / Ghid → <#{channel_ids['howto']}>\n"
            f"📰 Market News → <#{channel_ids['market_news']}>\n"
            f"💎 VIP Access → <#{channel_ids['get_vip']}>"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚡ Ce găsești aici",
        value=(
            "• semnale BUY/SELL cu Entry, TP și SL\n"
            "• știri crypto din surse publice reputabile\n"
            "• comenzi utile: `/help`, `/news`, `/fear`, `/coin`, `/multi`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🛡️ Risk-first mindset",
        value=(
            "• folosește mereu Stop Loss\n"
            "• nu intra all-in\n"
            "• verifică timeframe-uri multiple\n"
            "• educațional, nu sfat financiar"
        ),
        inline=True,
    )
    embed.add_field(
        name="✨ RCB style",
        value="Clean signal flow, Romanian + English onboarding, logo-branded embeds and less noise.",
        inline=False,
    )
    embed.set_footer(text=f"{BRAND_NAME} • Welcome system • Not financial advice")
    return embed


def build_member_welcome_embed(member: Any, channel_ids: dict[str, int]) -> discord.Embed:
    embed = discord.Embed(
        title=f"👋 Welcome, {getattr(member, 'display_name', 'trader')}! / Bun venit!",
        description=(
            "🇷🇴 **Bine ai venit în RCB Crypto AI.** Aici găsești semnale, news și ghiduri "
            "pentru trading disciplinat.\n"
            "🇬🇧 **Welcome to RCB Crypto AI.** You will find signals, market news and guides "
            "for disciplined trading.\n\n"
            f"{MINI_DIVIDER}"
        ),
        color=BRAND_BLUE,
    )
    embed.add_field(
        name="📍 Primii pași / First steps",
        value=(
            f"1️⃣ Citește regulile → <#{channel_ids['rules']}>\n"
            f"2️⃣ Vezi FAQ-ul → <#{channel_ids['faq']}>\n"
            f"3️⃣ Învață semnalele → <#{channel_ids['howto']}>\n"
            f"4️⃣ Urmărește market news → <#{channel_ids['market_news']}>"
        ),
        inline=False,
    )
    embed.add_field(
        name="💎 Pentru acces VIP / For VIP access",
        value=f"Intră aici / Go here → <#{channel_ids['get_vip']}>",
        inline=False,
    )
    embed.add_field(
        name="⚠️ Reminder",
        value="Signals are educational only. Use Stop Loss and manage risk.",
        inline=False,
    )
    avatar = getattr(getattr(member, "display_avatar", None), "url", None)
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text=f"{BRAND_NAME} • Welcome • Nu este sfat financiar")
    return embed


def build_market_news_intro_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📰 RCB Market News Desk",
        description=(
            "Curated crypto news with clean formatting, sentiment tags and transparent source labels.\n\n"
            "Știri crypto curatoriate cu format curat, sentiment și surse afișate transparent."
        ),
        color=BRAND_YELLOW,
    )
    embed.add_field(
        name="✅ Reliable public feeds",
        value=(
            "CoinDesk • The Block • Decrypt • Cointelegraph • Bitcoin Magazine • "
            "CryptoSlate • CoinGecko"
        ),
        inline=False,
    )
    embed.add_field(
        name="📌 What each post shows",
        value="headline, source, sentiment, short summary, link to the original article and risk reminder",
        inline=False,
    )
    embed.add_field(
        name="🧠 How to use it",
        value=(
            "Use news as context, not as a blind entry trigger. Confirm with chart structure, liquidity, "
            "timeframes and risk management."
        ),
        inline=False,
    )
    embed.set_footer(text=f"{BRAND_NAME} • Market News • Public feeds • Not financial advice")
    return embed


def build_market_news_embed(item: dict[str, Any], disclaimer_en: str = "Not financial advice", disclaimer_ro: str = "Nu este sfat financiar") -> discord.Embed:
    mood = item.get("mood", "⚪")
    mood_label = {
        "🟢": "Bullish / Pozitiv",
        "🔴": "Bearish / Negativ",
        "⚪": "Neutral / Neutru",
    }.get(mood, "Neutral / Neutru")
    color = {"🟢": BRAND_GREEN, "🔴": BRAND_RED, "⚪": BRAND_GREY}.get(mood, BRAND_BLUE)
    source = item.get("source", "Multi-source RSS")
    title = (item.get("title") or "Crypto market update")[:240]
    link = item.get("link") or None
    emoji = item.get("emoji", "📰")
    summary = _safe_field_value(item.get("summary", ""), 700)

    embed = discord.Embed(
        title=f"{emoji} {title}",
        url=link,
        description=(
            f"**Sentiment:** {mood} `{mood_label}`\n"
            f"**Source:** `{source}` — {item.get('reliability') or _source_reputation(str(source))}\n"
            f"**Desk note:** context only; wait for confirmation before acting."
        ),
        color=color,
    )
    if summary and summary != "—":
        embed.add_field(name="🧾 Quick summary", value=summary, inline=False)
    embed.add_field(
        name="✅ Trade checklist",
        value=(
            "• confirm trend + volume\n"
            "• check BTC/ETH correlation\n"
            "• define Entry, TP, SL before entering\n"
            "• avoid FOMO on fresh pumps"
        ),
        inline=True,
    )
    embed.add_field(
        name="🔗 Original article",
        value=f"[Open source article]({link})" if link else "Source link unavailable",
        inline=True,
    )
    embed.set_footer(text=f"{BRAND_NAME} Market News • {disclaimer_en} • {disclaimer_ro}")
    return embed


def build_faq_embeds(channel_ids: dict[str, int]) -> list[discord.Embed]:
    en = discord.Embed(
        title="❓ RCB FAQ — English",
        description=(
            "Quick answers for new members. Read this before trading any signal.\n"
            f"{DIVIDER}"
        ),
        color=BRAND_PURPLE,
    )
    en.add_field(
        name="1. What is RCB Crypto AI?",
        value="A Discord community with AI-assisted crypto signals, market news, education and tracking tools.",
        inline=False,
    )
    en.add_field(
        name="2. Are signals financial advice?",
        value="No. Signals are educational algorithmic opinions. You are responsible for every trade you take.",
        inline=False,
    )
    en.add_field(
        name="3. How do I read a signal?",
        value="Entry = planned entry price, TP = profit targets, SL = Stop Loss, confidence = quality filter.",
        inline=False,
    )
    en.add_field(
        name="4. What is Free vs VIP?",
        value=f"Free gives core signals and updates. VIP adds deeper signals, more confirmations and VIP tools → <#{channel_ids['get_vip']}>.",
        inline=False,
    )
    en.add_field(
        name="5. What risk should I use?",
        value="A common beginner rule is risking only 1–2% of the account per trade and never trading without SL.",
        inline=False,
    )
    en.add_field(
        name="6. Which commands matter first?",
        value="`/help`, `/news`, `/fear`, `/coin`, `/multi`, `/risk`, `/signals_explained`, `/firsttrade`.",
        inline=False,
    )
    en.add_field(
        name="7. Where are the channels?",
        value=(
            f"Welcome <#{channel_ids['welcome']}> • News <#{channel_ids['market_news']}> • "
            f"How-to <#{channel_ids['howto']}> • Rules <#{channel_ids['rules']}>"
        ),
        inline=False,
    )
    en.set_footer(text=f"{BRAND_NAME} FAQ • English • Not financial advice")

    ro = discord.Embed(
        title="❓ RCB FAQ — Română",
        description=(
            "Răspunsuri rapide pentru membrii noi. Citește înainte să intri pe orice semnal.\n"
            f"{DIVIDER}"
        ),
        color=BRAND_BLUE,
    )
    ro.add_field(
        name="1. Ce este RCB Crypto AI?",
        value="O comunitate Discord cu semnale crypto asistate de AI, market news, educație și tool-uri de tracking.",
        inline=False,
    )
    ro.add_field(
        name="2. Semnalele sunt sfaturi financiare?",
        value="Nu. Sunt opinii algoritmice educaționale. Fiecare trade este responsabilitatea ta.",
        inline=False,
    )
    ro.add_field(
        name="3. Cum citesc un semnal?",
        value="Entry = intrarea planificată, TP = ținte de profit, SL = Stop Loss, confidence = filtru de calitate.",
        inline=False,
    )
    ro.add_field(
        name="4. Ce diferență este între Free și VIP?",
        value=f"Free primește semnale de bază. VIP adaugă confirmări, semnale mai detaliate și tool-uri extra → <#{channel_ids['get_vip']}>.",
        inline=False,
    )
    ro.add_field(
        name="5. Ce risk management folosesc?",
        value="Regulă simplă pentru început: riști doar 1–2% din cont pe trade și nu intri fără Stop Loss.",
        inline=False,
    )
    ro.add_field(
        name="6. Ce comenzi folosesc prima dată?",
        value="`/help`, `/news`, `/fear`, `/coin`, `/multi`, `/risk`, `/signals_explained`, `/firsttrade`.",
        inline=False,
    )
    ro.add_field(
        name="7. Unde găsesc canalele?",
        value=(
            f"Welcome <#{channel_ids['welcome']}> • News <#{channel_ids['market_news']}> • "
            f"How-to <#{channel_ids['howto']}> • Rules <#{channel_ids['rules']}>"
        ),
        inline=False,
    )
    ro.set_footer(text=f"{BRAND_NAME} FAQ • Română • Nu este sfat financiar")
    return [en, ro]


async def setup_static_channels(
    *,
    client: discord.Client,
    fetch_message_channel: Callable[[int, str], Awaitable[discord.abc.Messageable | None]],
    channel_ids: dict[str, int],
) -> None:
    """Post the polished static content in Welcome, FAQ and Market News."""
    guild_name = client.guilds[0].name if getattr(client, "guilds", None) else None

    welcome_ch = await fetch_message_channel(channel_ids["welcome"], "WELCOME")
    await send_branded_once(
        welcome_ch,
        build_welcome_board(channel_ids, guild_name),
        "RCB Welcome Hub",
    )

    faq_ch = await fetch_message_channel(channel_ids["faq"], "FAQ")
    await send_branded_once(
        faq_ch,
        build_faq_embeds(channel_ids),
        "RCB FAQ",
    )

    news_ch = await fetch_message_channel(channel_ids["market_news"], "MARKET_NEWS")
    await send_branded_once(
        news_ch,
        build_market_news_intro_embed(),
        "RCB Market News Desk",
    )
