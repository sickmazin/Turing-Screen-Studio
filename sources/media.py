"""Song playing in Windows (System Media Transport Controls): Spotify, browsers, etc."""
import io
import time

from PIL import Image
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winsdk.windows.storage.streams import DataReader

name = "media"
settings = {}  # defaults, editable in the Data tab
interval = 1

PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
COVER_SETTLE = 8  # s: after a skip Windows may still hand out the previous song's thumbnail for a while
GAP_HOLD = 5      # s: between songs the session briefly reports nothing; keep showing the last song
_cover = {"key": None, "since": 0.0, "changed_at": 0.0, "bytes": None, "img": None}
_last = {"data": None, "at": 0.0}


async def _read_bytes(thumb):
    stream = await thumb.open_read_async()
    reader = DataReader(stream)
    await reader.load_async(stream.size)
    buf = bytearray(stream.size)
    reader.read_bytes(buf)
    return bytes(buf)


def update_cover(key, raw, now):
    """Keep one image per song; a new image object only when the thumbnail bytes really change."""
    if key != _cover["key"]:
        # the first song seen at start-up was not skipped to: trust Windows' position for it
        _cover.update(key=key, since=now, changed_at=time.time() if _cover["key"] is not None else 0.0)
    if raw != _cover["bytes"]:
        _cover["bytes"] = raw
        try:
            _cover["img"] = Image.open(io.BytesIO(raw)).convert("RGB") if raw else None
        except OSError:
            _cover["img"] = None
    return _cover["img"]


def live_position(position, updated_at, duration, playing, changed_at, now):
    """Windows reports the position only at its last update: add the time played since, from 0 after a skip.

    All times are wall-clock seconds (epoch)."""
    if updated_at < changed_at:  # timeline still belongs to the previous song
        position, updated_at = 0.0, changed_at
    if playing:
        position += max(0.0, now - updated_at)
    return min(position, duration) if duration > 0 else position


def hold(data, now):
    """The last song stays on screen for a few seconds while the next one is loading."""
    if data:
        _last.update(data=data, at=now)
        return data
    return _last["data"] if now - _last["at"] < GAP_HOLD else None


async def fetch(cfg):
    now = time.monotonic()
    manager = await SessionManager.request_async()
    session = manager.get_current_session()
    if not session:
        return hold(None, now)
    props = await session.try_get_media_properties_async()
    if not props.title:
        return hold(None, now)
    key = (props.title, props.artist)
    if key != _cover["key"] or now - _cover["since"] < COVER_SETTLE:  # re-read until the thumbnail settles
        try:
            raw = await _read_bytes(props.thumbnail) if props.thumbnail else None
        except Exception:
            raw = None
        update_cover(key, raw, now)
    tl = session.get_timeline_properties()
    playing = session.get_playback_info().playback_status == PLAYING
    duration = tl.end_time.total_seconds()
    try:
        updated_at = tl.last_updated_time.timestamp()
    except (AttributeError, OSError, ValueError):
        updated_at = time.time()
    return hold({
        "title": props.title,
        "artist": props.artist or "",
        "album": props.album_title or "",
        "position": live_position(tl.position.total_seconds(), updated_at, duration, playing, _cover["changed_at"],
                                  time.time()),
        "duration": duration,
        "playing": playing,
        "app": session.source_app_user_model_id,
        "cover": _cover["img"],
    }, now)
