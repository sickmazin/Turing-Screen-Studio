"""Brano in riproduzione da Windows (SMTC): Spotify, browser, ecc."""
import io

from PIL import Image
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winsdk.windows.storage.streams import DataReader

name = "media"
settings = {}  # valori predefiniti, modificabili da settings.py (scheda Dati)
interval = 1

PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
_cover = {"key": None, "img": None}


async def _read_cover(thumb):
    stream = await thumb.open_read_async()
    reader = DataReader(stream)
    await reader.load_async(stream.size)
    buf = bytearray(stream.size)
    reader.read_bytes(buf)
    return Image.open(io.BytesIO(bytes(buf))).convert("RGB")


async def fetch(cfg):
    manager = await SessionManager.request_async()
    session = manager.get_current_session()
    if not session:
        return None
    props = await session.try_get_media_properties_async()
    tl = session.get_timeline_properties()
    key = (props.title, props.artist)
    if key != _cover["key"]:
        _cover["key"] = key
        try:
            _cover["img"] = await _read_cover(props.thumbnail) if props.thumbnail else None
        except Exception:
            _cover["img"] = None
    return {
        "title": props.title or "",
        "artist": props.artist or "",
        "album": props.album_title or "",
        "position": tl.position.total_seconds(),
        "duration": tl.end_time.total_seconds(),
        "playing": session.get_playback_info().playback_status == PLAYING,
        "app": session.source_app_user_model_id,
        "cover": _cover["img"],
    }
