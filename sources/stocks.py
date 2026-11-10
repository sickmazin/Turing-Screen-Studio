"""Quotes from the Yahoo Finance chart endpoint.

shortcut: unofficial endpoint, it may change; if it breaks only _get() needs replacing.
"""
import asyncio

import requests

name = "stocks"
settings = {"tickers": ["AAPL", "NVDA", "MSFT", "BTC-USD", "^GSPC"]}  # defaults, editable in the Data tab
interval = 60

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
HEADERS = {"User-Agent": "Mozilla/5.0"}  # without a User-Agent Yahoo answers 429


def _get(symbol):
    r = requests.get(URL.format(symbol), params={"range": "1d", "interval": "5m"}, headers=HEADERS, timeout=10)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    meta = res["meta"]
    closes = [c for c in res["indicators"]["quote"][0].get("close") or [] if c is not None]
    price = meta["regularMarketPrice"]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
    return {"symbol": symbol, "price": price, "prev": prev, "change": (price - prev) / prev * 100 if prev else 0,
            "currency": meta.get("currency", ""), "series": closes}


async def fetch(cfg):
    symbols = cfg.get("tickers", ["AAPL", "NVDA", "BTC-USD"])
    results = await asyncio.gather(*(asyncio.to_thread(_get, s) for s in symbols), return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]
