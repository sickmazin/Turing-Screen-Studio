"""Weather from Open-Meteo (free, no API key)."""
import asyncio

import requests

name = "weather"
settings = {"city": "Milano", "lat": 45.46, "lon": 9.19}  # defaults, editable in the Data tab
interval = 600

URL = "https://api.open-meteo.com/v1/forecast"


def _get(cfg):
    r = requests.get(URL, timeout=10, params={
        "latitude": cfg.get("lat", 45.46), "longitude": cfg.get("lon", 9.19),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 5,
    })
    r.raise_for_status()
    return r.json()


async def fetch(cfg):
    j = await asyncio.to_thread(_get, cfg)
    c, d = j["current"], j["daily"]
    return {
        "city": cfg.get("city", ""),
        "temp": c["temperature_2m"], "feels": c["apparent_temperature"],
        "humidity": c["relative_humidity_2m"], "wind": c["wind_speed_10m"],
        "code": c["weather_code"], "is_day": bool(c["is_day"]),
        "days": [
            {"date": d["time"][i], "code": d["weather_code"][i], "max": d["temperature_2m_max"][i],
             "min": d["temperature_2m_min"][i], "rain": d["precipitation_probability_max"][i]}
            for i in range(len(d["time"]))
        ],
    }
