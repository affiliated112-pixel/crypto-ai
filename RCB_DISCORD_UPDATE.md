# RCB Discord aesthetic update

Modificări incluse în această arhivă:

## Canale configurate

```env
WELCOME_CHANNEL=1509522341074567208
MARKET_NEWS_CHANNEL=1509522484594999387
FAQ_CHANNEL=1509524421675847913
BRAND_NAME=RCB Crypto AI
```

## Ce s-a schimbat

- Am adăugat sigla în `assets/rcb-logo.png` și un modul nou `community_embeds.py` pentru embed-uri premium Discord.
- Canalul de welcome primește un **RCB Welcome Hub** static la pornire și un mesaj mai curat pentru fiecare membru nou.
- Canalul de FAQ primește două embed-uri: **English FAQ** și **Romanian FAQ**.
- Canalul de market news primește un **RCB Market News Desk** și știri formatate cu:
  - sursă afișată transparent;
  - sentiment bullish/bearish/neutral;
  - summary scurt;
  - link la articolul original;
  - checklist de risk management.
- Sursele de news au fost curățate spre feed-uri mai reputabile: CoinDesk, The Block, Decrypt, Cointelegraph, Bitcoin Magazine, CryptoSlate și CoinGecko.
- Embed-urile trimise de bot folosesc logo-ul local când botul are permisiunea **Attach Files**.

## Permisiuni Discord necesare

Pentru canalele de welcome, FAQ și market-news, botul trebuie să aibă:

- Send Messages
- Embed Links
- Attach Files
- Read Message History

`Read Message History` ajută botul să nu reposteze aceleași mesaje statice la fiecare restart.
