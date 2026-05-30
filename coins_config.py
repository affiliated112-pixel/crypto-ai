"""coins_config.py — Central registry for all supported coins.

FREE tier scans: TOP_FREE_SYMBOLS (6 major coins)
VIP tier scans:  ALL_VIP_SYMBOLS  (30 coins — majors + mid-caps + altcoins)

To add a new coin:
  1. Add to COIN_META dict below
  2. Add to FREE_SYMBOLS or VIP_ONLY_SYMBOLS list
  3. Verify it has real public market data (Binance Global/US or CoinGecko fallback)
"""

# ─── COIN METADATA ────────────────────────────────────────────────────────────
# Each entry: symbol -> {emoji, name_en, color (discord embed hex), logo_url}
COIN_META = {
    # ── MEGA CAP ──────────────────────────────────────────────────────────────
    "BTCUSDT": {
        "emoji":   "₿",
        "name":    "Bitcoin (BTC)",
        "color":   0xF7931A,
        "logo":    "https://assets.coingecko.com/coins/images/1/small/bitcoin.png",
        "tier":    "free",
    },
    "ETHUSDT": {
        "emoji":   "Ξ",
        "name":    "Ethereum (ETH)",
        "color":   0x627EEA,
        "logo":    "https://assets.coingecko.com/coins/images/279/small/ethereum.png",
        "tier":    "free",
    },
    # ── LARGE CAP FREE ────────────────────────────────────────────────────────
    "SOLUSDT": {
        "emoji":   "◎",
        "name":    "Solana (SOL)",
        "color":   0x9945FF,
        "logo":    "https://assets.coingecko.com/coins/images/4128/small/solana.png",
        "tier":    "free",
    },
    "BNBUSDT": {
        "emoji":   "⬡",
        "name":    "BNB Chain (BNB)",
        "color":   0xF0B90B,
        "logo":    "https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png",
        "tier":    "free",
    },
    "XRPUSDT": {
        "emoji":   "✕",
        "name":    "XRP (XRP)",
        "color":   0x00AAE4,
        "logo":    "https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png",
        "tier":    "free",
    },
    "DOGEUSDT": {
        "emoji":   "🐶",
        "name":    "Dogecoin (DOGE)",
        "color":   0xC3A634,
        "logo":    "https://assets.coingecko.com/coins/images/5/small/dogecoin.png",
        "tier":    "free",
    },
    # ── VIP ONLY — LARGE CAP ──────────────────────────────────────────────────
    "ADAUSDT": {
        "emoji":   "₳",
        "name":    "Cardano (ADA)",
        "color":   0x0033AD,
        "logo":    "https://assets.coingecko.com/coins/images/975/small/cardano.png",
        "tier":    "vip",
    },
    "AVAXUSDT": {
        "emoji":   "🔺",
        "name":    "Avalanche (AVAX)",
        "color":   0xE84142,
        "logo":    "https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png",
        "tier":    "vip",
    },
    "DOTUSDT": {
        "emoji":   "●",
        "name":    "Polkadot (DOT)",
        "color":   0xE6007A,
        "logo":    "https://assets.coingecko.com/coins/images/12171/small/polkadot.png",
        "tier":    "vip",
    },
    "LINKUSDT": {
        "emoji":   "⛓",
        "name":    "Chainlink (LINK)",
        "color":   0x2A5ADA,
        "logo":    "https://assets.coingecko.com/coins/images/877/small/chainlink-new-logo.png",
        "tier":    "vip",
    },
    "LTCUSDT": {
        "emoji":   "Ł",
        "name":    "Litecoin (LTC)",
        "color":   0xBFBFBF,
        "logo":    "https://assets.coingecko.com/coins/images/2/small/litecoin.png",
        "tier":    "vip",
    },
    "MATICUSDT": {
        "emoji":   "🔷",
        "name":    "Polygon (MATIC)",
        "color":   0x8247E5,
        "logo":    "https://assets.coingecko.com/coins/images/4713/small/matic-token-icon.png",
        "tier":    "vip",
    },
    "UNIUSDT": {
        "emoji":   "🦄",
        "name":    "Uniswap (UNI)",
        "color":   0xFF007A,
        "logo":    "https://assets.coingecko.com/coins/images/12504/small/uniswap-uni.png",
        "tier":    "vip",
    },
    "ATOMUSDT": {
        "emoji":   "⚛",
        "name":    "Cosmos (ATOM)",
        "color":   0x2E3148,
        "logo":    "https://assets.coingecko.com/coins/images/1481/small/cosmos_hub.png",
        "tier":    "vip",
    },
    "XLMUSDT": {
        "emoji":   "✦",
        "name":    "Stellar (XLM)",
        "color":   0x14B6E7,
        "logo":    "https://assets.coingecko.com/coins/images/100/small/Stellar_symbol_black_RGB.png",
        "tier":    "vip",
    },
    "NEARUSDT": {
        "emoji":   "Ⓝ",
        "name":    "NEAR Protocol (NEAR)",
        "color":   0x00C08B,
        "logo":    "https://assets.coingecko.com/coins/images/10365/small/near.jpg",
        "tier":    "vip",
    },
    "FTMUSDT": {
        "emoji":   "👻",
        "name":    "Fantom (FTM)",
        "color":   0x1969FF,
        "logo":    "https://assets.coingecko.com/coins/images/4001/small/Fantom_round.png",
        "tier":    "vip",
    },
    "ALGOUSDT": {
        "emoji":   "△",
        "name":    "Algorand (ALGO)",
        "color":   0x000000,
        "logo":    "https://assets.coingecko.com/coins/images/4380/small/download.png",
        "tier":    "vip",
    },
    "SANDUSDT": {
        "emoji":   "🏖",
        "name":    "The Sandbox (SAND)",
        "color":   0x04ADEF,
        "logo":    "https://assets.coingecko.com/coins/images/12129/small/sandbox_logo.jpg",
        "tier":    "vip",
    },
    "MANAUSDT": {
        "emoji":   "🌐",
        "name":    "Decentraland (MANA)",
        "color":   0xFF2D55,
        "logo":    "https://assets.coingecko.com/coins/images/878/small/decentraland-mana.png",
        "tier":    "vip",
    },
    "FILUSDT": {
        "emoji":   "📁",
        "name":    "Filecoin (FIL)",
        "color":   0x0090FF,
        "logo":    "https://assets.coingecko.com/coins/images/12817/small/filecoin.png",
        "tier":    "vip",
    },
    "TRXUSDT": {
        "emoji":   "♦",
        "name":    "TRON (TRX)",
        "color":   0xEB0029,
        "logo":    "https://assets.coingecko.com/coins/images/1094/small/tron-logo.png",
        "tier":    "vip",
    },
    "ETCUSDT": {
        "emoji":   "⬡",
        "name":    "Ethereum Classic (ETC)",
        "color":   0x328332,
        "logo":    "https://assets.coingecko.com/coins/images/453/small/ethereum-classic-logo.png",
        "tier":    "vip",
    },
    "AAVEUSDT": {
        "emoji":   "👻",
        "name":    "Aave (AAVE)",
        "color":   0xB6509E,
        "logo":    "https://assets.coingecko.com/coins/images/12645/small/AAVE.png",
        "tier":    "vip",
    },
    "GRTUSDT": {
        "emoji":   "📊",
        "name":    "The Graph (GRT)",
        "color":   0x6F4CBA,
        "logo":    "https://assets.coingecko.com/coins/images/13397/small/Graph_Token.png",
        "tier":    "vip",
    },
    "SHIBUSDT": {
        "emoji":   "🐕",
        "name":    "Shiba Inu (SHIB)",
        "color":   0xFFA409,
        "logo":    "https://assets.coingecko.com/coins/images/11939/small/shiba.png",
        "tier":    "vip",
    },
    "OPUSDT": {
        "emoji":   "🔴",
        "name":    "Optimism (OP)",
        "color":   0xFF0420,
        "logo":    "https://assets.coingecko.com/coins/images/25244/small/Optimism.png",
        "tier":    "vip",
    },
    "ARBUSDT": {
        "emoji":   "🔵",
        "name":    "Arbitrum (ARB)",
        "color":   0x2D374B,
        "logo":    "https://assets.coingecko.com/coins/images/16547/small/photo_2023-03-29_21.47.00.jpeg",
        "tier":    "vip",
    },
    "INJUSDT": {
        "emoji":   "💉",
        "name":    "Injective (INJ)",
        "color":   0x00B2FF,
        "logo":    "https://assets.coingecko.com/coins/images/12882/small/Secondary_Symbol.png",
        "tier":    "vip",
    },
    "SUIUSDT": {
        "emoji":   "💧",
        "name":    "Sui (SUI)",
        "color":   0x4DA2FF,
        "logo":    "https://assets.coingecko.com/coins/images/26375/small/sui_asset.jpeg",
        "tier":    "vip",
    },
    "APTUSDT": {
        "emoji":   "🌀",
        "name":    "Aptos (APT)",
        "color":   0x00C2B3,
        "logo":    "https://assets.coingecko.com/coins/images/26455/small/aptos_round.png",
        "tier":    "vip",
    },
}

# ─── SYMBOL LISTS ─────────────────────────────────────────────────────────────

FREE_SYMBOLS: list[str] = [
    sym for sym, meta in COIN_META.items() if meta["tier"] == "free"
]

VIP_ONLY_SYMBOLS: list[str] = [
    sym for sym, meta in COIN_META.items() if meta["tier"] == "vip"
]

ALL_VIP_SYMBOLS: list[str] = FREE_SYMBOLS + VIP_ONLY_SYMBOLS

# ─── CONVENIENCE DICTS (drop-in replacements for bot.py dicts) ────────────────

COIN_COLORS:   dict[str, int] = {sym: m["color"] for sym, m in COIN_META.items()}
COIN_EMOJI:    dict[str, str] = {sym: m["emoji"] for sym, m in COIN_META.items()}
COIN_NAMES_EN: dict[str, str] = {sym: m["name"]  for sym, m in COIN_META.items()}
COIN_LOGOS:    dict[str, str] = {sym: m["logo"]  for sym, m in COIN_META.items()}

# ─── COINGECKO SLUG MAP (for metrics) ─────────────────────────────────────────
COINGECKO_SLUG: dict[str, str] = {
    "BTCUSDT":   "bitcoin",
    "ETHUSDT":   "ethereum",
    "SOLUSDT":   "solana",
    "BNBUSDT":   "binancecoin",
    "XRPUSDT":   "ripple",
    "DOGEUSDT":  "dogecoin",
    "ADAUSDT":   "cardano",
    "AVAXUSDT":  "avalanche-2",
    "DOTUSDT":   "polkadot",
    "LINKUSDT":  "chainlink",
    "LTCUSDT":   "litecoin",
    "MATICUSDT": "matic-network",
    "UNIUSDT":   "uniswap",
    "ATOMUSDT":  "cosmos",
    "XLMUSDT":   "stellar",
    "NEARUSDT":  "near",
    "FTMUSDT":   "fantom",
    "ALGOUSDT":  "algorand",
    "SANDUSDT":  "the-sandbox",
    "MANAUSDT":  "decentraland",
    "FILUSDT":   "filecoin",
    "TRXUSDT":   "tron",
    "ETCUSDT":   "ethereum-classic",
    "AAVEUSDT":  "aave",
    "GRTUSDT":   "the-graph",
    "SHIBUSDT":  "shiba-inu",
    "OPUSDT":    "optimism",
    "ARBUSDT":   "arbitrum",
    "INJUSDT":   "injective-protocol",
    "SUIUSDT":   "sui",
    "APTUSDT":   "aptos",
}
