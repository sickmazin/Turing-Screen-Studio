"""Small logos for market symbols, downloaded once into <data>/logos-v2.

Sources, in order: github.com/davidepalazzo/ticker-logos (transparent, made for dark themes: US stocks and ETFs,
crypto, forex), then financialmodelingprep.com (European and Italian stocks and ETFs).

Symbols with no logo get an emoji (currencies, commodities) or a country badge (indices): the Windows emoji font
has no flags. Logos are fetched at runtime and never stored in the repository.
"""
import re
import time
from io import BytesIO

import requests
from PIL import Image, ImageChops, ImageStat

import paths
from stock_catalog import CATALOG

REPO = "https://raw.githubusercontent.com/davidepalazzo/ticker-logos/main/"
FMP_URL = "https://financialmodelingprep.com/image-stock/{}.png"
REPO_NAMES = {"BRK-B": "BRKA"}  # the repo has one logo per company
HEADERS = {"User-Agent": "Mozilla/5.0"}
RETRY_MISSING = 7 * 86400  # a symbol with no logo is asked again after a week
MAX_BYTES = 1_000_000      # files come from a third-party site
CRYPTO = {s for s, _n in CATALOG["Crypto"]}
EMOJI = {"GC=F": "🥇", "SI=F": "🥈", "PL=F": "⚪", "HG=F": "🟠", "CL=F": "🛢️", "BZ=F": "🛢️", "NG=F": "🔥",
         "ZW=F": "🌾", "EURUSD=X": "💶", "EURCHF=X": "💶", "EURGBP=X": "💶", "GBPUSD=X": "💷", "USDJPY=X": "💴",
         "DX-Y.NYB": "💵",
         # gold/silver ETFs: their logos are a plain bar shape that turns into a blank rectangle once recoloured
         "GLD": "🥇", "IGLN.L": "🥇", "PHAU.MI": "🥇", "SLV": "🥈"}
COUNTRY = {"^GSPC": "US", "^IXIC": "US", "^NDX": "US", "^DJI": "US", "^RUT": "US", "^VIX": "US", "^STOXX50E": "EU",
           "^GDAXI": "DE", "^FCHI": "FR", "FTSEMIB.MI": "IT", "^FTSE": "UK", "^IBEX": "ES", "^SSMI": "CH",
           "^N225": "JP", "^HSI": "HK", "000001.SS": "CN"}
_mem = {}


def urls(symbol: str):
    """Where to look for this symbol's logo, best source first."""
    if symbol in EMOJI and not symbol.endswith("=X") or symbol in COUNTRY or symbol.startswith("^") or "=F" in symbol:
        return []
    if symbol.endswith("=X"):
        return [REPO + f"forex_icons/{symbol[:-2]}.png"]
    if symbol in CRYPTO or re.fullmatch(r"[A-Z0-9]+-(USD|EUR)", symbol):
        return [REPO + f"crypto_icons/{symbol.split('-')[0]}.png"]
    found = [FMP_URL.format(symbol)]
    if "." not in symbol:  # US listing: the repo first
        found.insert(0, REPO + f"ticker_icons/{REPO_NAMES.get(symbol, symbol.replace('-', '.'))}.png")
    return found


def logo(symbol: str):
    """The symbol's logo as an RGBA image, or None. Uses the network only the first time."""
    if symbol in _mem:
        return _mem[symbol]
    sources = urls(symbol)
    if not sources:
        _mem[symbol] = None
        return None
    folder = paths.DATA / "logos-v2"
    file = folder / (re.sub(r"[^A-Za-z0-9._-]", "_", symbol) + ".png")
    missing = file.with_suffix(".none")
    img = None
    if file.exists():
        try:
            img = Image.open(file).convert("RGBA")
        except OSError:
            file.unlink(missing_ok=True)
    elif not (missing.exists() and time.time() - missing.stat().st_mtime < RETRY_MISSING):
        for u in sources:
            try:
                r = requests.get(u, headers=HEADERS, timeout=10)
                r.raise_for_status()
                if len(r.content) > MAX_BYTES:
                    raise ValueError("logo too large")
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                img.thumbnail((128, 128))
                folder.mkdir(parents=True, exist_ok=True)
                img.save(file)
                break
            except requests.HTTPError:  # 404: not in this source, try the next one
                continue
            except (requests.RequestException, OSError, ValueError):
                return None  # offline or a bad file: try again on the next refresh, remember nothing
        else:
            folder.mkdir(parents=True, exist_ok=True)
            missing.touch()  # no source has it
    _mem[symbol] = img
    return img


def is_monochrome(img) -> bool:
    """Black, white or grey logo (on transparency): it can take the theme's text colour."""
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] > 250:
        return False  # fully opaque: the logo has its own background, keep it
    r, g, b = img.convert("RGB").split()
    chroma = ImageChops.subtract(ImageChops.lighter(ImageChops.lighter(r, g), b), ImageChops.darker(ImageChops.darker(r, g), b))
    visible = alpha.point(lambda v: 255 if v > 128 else 0)
    if not visible.getbbox():
        return False
    return ImageStat.Stat(chroma, mask=visible).mean[0] < 30  # average colourfulness of the visible pixels
