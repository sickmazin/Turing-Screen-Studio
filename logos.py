"""Small logos for market symbols, downloaded once into <data>/logos (stocks and ETFs, crypto).

Symbols with no logo get an emoji (currencies, commodities) or a country badge (indices): the Windows emoji font
has no flags. Logos are fetched at runtime and never stored in the repository.
"""
import re
import time
from io import BytesIO

import requests
from PIL import Image

import paths
from stock_catalog import CATALOG

STOCK_URL = "https://financialmodelingprep.com/image-stock/{}.png"
CRYPTO_URL = "https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{}.png"
HEADERS = {"User-Agent": "Mozilla/5.0"}
RETRY_MISSING = 7 * 86400  # a symbol with no logo is asked again after a week
MAX_BYTES = 1_000_000      # files come from a third-party site
CRYPTO = {s for s, _n in CATALOG["Crypto"]}
EMOJI = {"GC=F": "🥇", "SI=F": "🥈", "PL=F": "⚪", "HG=F": "🟠", "CL=F": "🛢️", "BZ=F": "🛢️", "NG=F": "🔥",
         "ZW=F": "🌾", "EURUSD=X": "💶", "EURCHF=X": "💶", "EURGBP=X": "💶", "GBPUSD=X": "💷", "USDJPY=X": "💴",
         "DX-Y.NYB": "💵"}
COUNTRY = {"^GSPC": "US", "^IXIC": "US", "^NDX": "US", "^DJI": "US", "^RUT": "US", "^VIX": "US", "^STOXX50E": "EU",
           "^GDAXI": "DE", "^FCHI": "FR", "FTSEMIB.MI": "IT", "^FTSE": "UK", "^IBEX": "ES", "^SSMI": "CH",
           "^N225": "JP", "^HSI": "HK", "000001.SS": "CN"}
_mem = {}


def url(symbol: str):
    if symbol in EMOJI or symbol in COUNTRY or symbol.startswith("^") or "=" in symbol:
        return None
    if symbol in CRYPTO or re.fullmatch(r"[A-Z0-9]+-(USD|EUR)", symbol):
        return CRYPTO_URL.format(symbol.split("-")[0].lower())
    return STOCK_URL.format(symbol)


def logo(symbol: str):
    """The symbol's logo as an RGBA image, or None. Uses the network only the first time."""
    if symbol in _mem:
        return _mem[symbol]
    u = url(symbol)
    if not u:
        _mem[symbol] = None
        return None
    folder = paths.DATA / "logos"
    file = folder / (re.sub(r"[^A-Za-z0-9._-]", "_", symbol) + ".png")
    missing = file.with_suffix(".none")
    img = None
    if file.exists():
        try:
            img = Image.open(file).convert("RGBA")
        except OSError:
            file.unlink(missing_ok=True)
    elif not (missing.exists() and time.time() - missing.stat().st_mtime < RETRY_MISSING):
        try:
            r = requests.get(u, headers=HEADERS, timeout=10)
            r.raise_for_status()
            if len(r.content) > MAX_BYTES:
                raise ValueError("logo too large")
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            img.thumbnail((128, 128))
            folder.mkdir(parents=True, exist_ok=True)
            img.save(file)
        except requests.HTTPError:  # 404: this symbol has no logo
            folder.mkdir(parents=True, exist_ok=True)
            missing.touch()
        except (requests.RequestException, OSError, ValueError):
            return None  # offline or a bad file: try again on the next refresh, remember nothing
    _mem[symbol] = img
    return img
