"""Symbols offered in the Markets picker: Yahoo Finance tickers, all checked against Yahoo on 2026-11-10.

Any other Yahoo symbol can still be typed by hand in the picker.
"""

CATALOG = {
    "US stocks": [
        ('AAPL', 'Apple'), ('MSFT', 'Microsoft'), ('NVDA', 'NVIDIA'), ('AMZN', 'Amazon'), ('GOOGL', 'Alphabet'),
        ('META', 'Meta Platforms'), ('TSLA', 'Tesla'), ('AVGO', 'Broadcom'), ('BRK-B', 'Berkshire Hathaway'),
        ('JPM', 'JPMorgan Chase'), ('V', 'Visa'), ('MA', 'Mastercard'), ('UNH', 'UnitedHealth'),
        ('XOM', 'Exxon Mobil'), ('JNJ', 'Johnson & Johnson'), ('PG', 'Procter & Gamble'), ('HD', 'Home Depot'),
        ('COST', 'Costco'), ('ABBV', 'AbbVie'), ('LLY', 'Eli Lilly'), ('MRK', 'Merck & Co.'), ('PEP', 'PepsiCo'),
        ('KO', 'Coca-Cola'), ('BAC', 'Bank of America'), ('WMT', 'Walmart'), ('NFLX', 'Netflix'), ('ADBE', 'Adobe'),
        ('CRM', 'Salesforce'), ('ORCL', 'Oracle'), ('AMD', 'AMD'), ('INTC', 'Intel'), ('QCOM', 'Qualcomm'),
        ('TXN', 'Texas Instruments'), ('CSCO', 'Cisco'), ('IBM', 'IBM'), ('DIS', 'Disney'), ('NKE', 'Nike'),
        ('MCD', "McDonald's"), ('SBUX', 'Starbucks'), ('BA', 'Boeing'), ('CAT', 'Caterpillar'),
        ('GE', 'GE Aerospace'), ('PFE', 'Pfizer'), ('T', 'AT&T'), ('VZ', 'Verizon'), ('PYPL', 'PayPal'),
        ('UBER', 'Uber'), ('ABNB', 'Airbnb'), ('SHOP', 'Shopify'), ('PLTR', 'Palantir'), ('COIN', 'Coinbase'),
        ('SNOW', 'Snowflake'), ('ARM', 'Arm Holdings'), ('MU', 'Micron'), ('ASML', 'ASML (NASDAQ)'),
        ('TSM', 'TSMC'), ('BABA', 'Alibaba'), ('SONY', 'Sony'), ('TM', 'Toyota'), ('GS', 'Goldman Sachs'),
        ('MS', 'Morgan Stanley'), ('SPOT', 'Spotify'), ('RBLX', 'Roblox'), ('MSTR', 'MicroStrategy'),
        ('SMCI', 'Super Micro Computer'), ('DELL', 'Dell'), ('HOOD', 'Robinhood'),
    ],
    "European stocks": [
        ('SAP.DE', 'SAP'), ('SIE.DE', 'Siemens'), ('ALV.DE', 'Allianz'), ('BMW.DE', 'BMW'),
        ('MBG.DE', 'Mercedes-Benz'), ('VOW3.DE', 'Volkswagen'), ('ADS.DE', 'Adidas'),
        ('DTE.DE', 'Deutsche Telekom'), ('RHM.DE', 'Rheinmetall'), ('AIR.PA', 'Airbus'), ('MC.PA', 'LVMH'),
        ('OR.PA', "L'Oréal"), ('TTE.PA', 'TotalEnergies'), ('SAN.PA', 'Sanofi'), ('BNP.PA', 'BNP Paribas'),
        ('RMS.PA', 'Hermès'), ('ASML.AS', 'ASML (Amsterdam)'), ('ADYEN.AS', 'Adyen'), ('NESN.SW', 'Nestlé'),
        ('NOVN.SW', 'Novartis'), ('RO.SW', 'Roche'), ('UBSG.SW', 'UBS'), ('NOVO-B.CO', 'Novo Nordisk'),
        ('SHEL.L', 'Shell'), ('AZN.L', 'AstraZeneca'), ('HSBA.L', 'HSBC'), ('ULVR.L', 'Unilever'), ('BP.L', 'BP'),
        ('RR.L', 'Rolls-Royce'), ('SAN.MC', 'Banco Santander'), ('ITX.MC', 'Inditex'), ('IBE.MC', 'Iberdrola'),
    ],
    "Italian stocks": [
        ('ENI.MI', 'Eni'), ('ENEL.MI', 'Enel'), ('ISP.MI', 'Intesa Sanpaolo'), ('UCG.MI', 'UniCredit'),
        ('STLAM.MI', 'Stellantis'), ('RACE.MI', 'Ferrari'), ('G.MI', 'Generali'), ('TIT.MI', 'Telecom Italia'),
        ('LDO.MI', 'Leonardo'), ('PST.MI', 'Poste Italiane'), ('MONC.MI', 'Moncler'), ('PRY.MI', 'Prysmian'),
        ('STMMI.MI', 'STMicroelectronics'), ('TEN.MI', 'Tenaris'), ('MB.MI', 'Mediobanca'),
        ('BAMI.MI', 'Banco BPM'), ('SRG.MI', 'Snam'), ('TRN.MI', 'Terna'), ('CPR.MI', 'Campari'), ('A2A.MI', 'A2A'),
        ('NEXI.MI', 'Nexi'), ('AMP.MI', 'Amplifon'), ('DIA.MI', 'DiaSorin'), ('REC.MI', 'Recordati'),
        ('BMED.MI', 'Banca Mediolanum'), ('FBK.MI', 'FinecoBank'), ('IVG.MI', 'Iveco'),
        ('BC.MI', 'Brunello Cucinelli'), ('BMPS.MI', 'Monte dei Paschi'), ('BPE.MI', 'BPER Banca'),
        ('HER.MI', 'Hera'), ('INW.MI', 'Inwit'), ('PIRC.MI', 'Pirelli'), ('SPM.MI', 'Saipem'), ('UNI.MI', 'Unipol'),
        ('AZM.MI', 'Azimut'), ('ERG.MI', 'ERG'), ('IP.MI', 'Interpump'),
    ],
    "ETF": [
        ('SPY', 'SPDR S&P 500'), ('QQQ', 'Invesco QQQ (Nasdaq-100)'), ('VOO', 'Vanguard S&P 500'),
        ('VTI', 'Vanguard Total Stock Market'), ('IWM', 'iShares Russell 2000'), ('DIA', 'SPDR Dow Jones'),
        ('VEA', 'Vanguard Developed Markets'), ('VWO', 'Vanguard Emerging Markets'), ('EFA', 'iShares MSCI EAFE'),
        ('AGG', 'iShares Core US Aggregate Bond'), ('BND', 'Vanguard Total Bond'),
        ('TLT', 'iShares 20+ Year Treasury'), ('GLD', 'SPDR Gold'), ('SLV', 'iShares Silver'),
        ('XLK', 'Technology Select Sector'), ('XLF', 'Financial Select Sector'), ('XLE', 'Energy Select Sector'),
        ('ARKK', 'ARK Innovation'), ('SMH', 'VanEck Semiconductor'), ('SOXX', 'iShares Semiconductor'),
        ('VNQ', 'Vanguard Real Estate'), ('SCHD', 'Schwab US Dividend Equity'), ('IBIT', 'iShares Bitcoin Trust'),
        ('SWDA.MI', 'iShares Core MSCI World (Milano)'), ('CSSPX.MI', 'iShares Core S&P 500 (Milano)'),
        ('EIMI.MI', 'iShares Core MSCI EM IMI (Milano)'), ('VWCE.DE', 'Vanguard FTSE All-World (Xetra)'),
        ('IWDA.AS', 'iShares Core MSCI World (Amsterdam)'), ('VUSA.AS', 'Vanguard S&P 500 (Amsterdam)'),
        ('CSPX.L', 'iShares Core S&P 500 (Londra)'), ('EQQQ.MI', 'Invesco Nasdaq-100 (Milano)'),
        ('VUAA.MI', 'Vanguard S&P 500 Acc (Milano)'), ('IGLN.L', 'iShares Physical Gold (Londra)'),
        ('PHAU.MI', 'WisdomTree Physical Gold (Milano)'), ('XDWD.DE', 'Xtrackers MSCI World (Xetra)'),
    ],
    "Indices": [
        ('^GSPC', 'S&P 500'), ('^IXIC', 'Nasdaq Composite'), ('^NDX', 'Nasdaq 100'), ('^DJI', 'Dow Jones'),
        ('^RUT', 'Russell 2000'), ('^VIX', 'VIX'), ('^STOXX50E', 'Euro Stoxx 50'), ('^GDAXI', 'DAX'),
        ('^FCHI', 'CAC 40'), ('FTSEMIB.MI', 'FTSE MIB'), ('^FTSE', 'FTSE 100'), ('^IBEX', 'IBEX 35'),
        ('^SSMI', 'SMI'), ('^N225', 'Nikkei 225'), ('^HSI', 'Hang Seng'), ('000001.SS', 'Shanghai Composite'),
    ],
    "Commodities & FX": [
        ('GC=F', 'Oro'), ('SI=F', 'Argento'), ('CL=F', 'Petrolio WTI'), ('BZ=F', 'Petrolio Brent'),
        ('NG=F', 'Gas naturale'), ('HG=F', 'Rame'), ('PL=F', 'Platino'), ('ZW=F', 'Grano'),
        ('EURUSD=X', 'EUR / USD'), ('GBPUSD=X', 'GBP / USD'), ('USDJPY=X', 'USD / JPY'), ('EURCHF=X', 'EUR / CHF'),
        ('EURGBP=X', 'EUR / GBP'), ('DX-Y.NYB', 'Indice del dollaro'),
    ],
    "Crypto": [
        ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('SOL-USD', 'Solana'), ('XRP-USD', 'XRP'),
        ('BNB-USD', 'BNB'), ('ADA-USD', 'Cardano'), ('DOGE-USD', 'Dogecoin'), ('TRX-USD', 'TRON'),
        ('AVAX-USD', 'Avalanche'), ('DOT-USD', 'Polkadot'), ('LINK-USD', 'Chainlink'), ('LTC-USD', 'Litecoin'),
        ('BCH-USD', 'Bitcoin Cash'), ('XLM-USD', 'Stellar'), ('ATOM-USD', 'Cosmos'), ('NEAR-USD', 'NEAR Protocol'),
        ('SHIB-USD', 'Shiba Inu'), ('HBAR-USD', 'Hedera'), ('XMR-USD', 'Monero'), ('ETC-USD', 'Ethereum Classic'),
        ('BTC-EUR', 'Bitcoin (EUR)'), ('ETH-EUR', 'Ethereum (EUR)'),
    ],
}

NAMES = {s: n for items in CATALOG.values() for s, n in items}
