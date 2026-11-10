"""Recent Windows notifications (Action Center), newest first.

Windows asks once for permission ("Allow access to notifications"). Data: notifications.N.{app, title, body, time}
"""
from datetime import datetime

name = "notifications"
settings = {"max": 10, "hide_apps": []}
interval = 5


async def fetch(cfg):
    from winsdk.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
    from winsdk.windows.ui.notifications.management import UserNotificationListener

    listener = UserNotificationListener.current
    if int(await listener.request_access_async()) != 1:  # 1 = allowed
        return None
    hidden = {a.lower() for a in cfg.get("hide_apps") or []}
    out = []
    for n in await listener.get_notifications_async(NotificationKinds.TOAST):
        try:
            app = n.app_info.display_info.display_name
        except OSError:
            app = ""
        if app.lower() in hidden:
            continue
        binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
        texts = [t.text for t in binding.get_text_elements()] if binding else []
        created = datetime.fromtimestamp(n.creation_time.timestamp()) if hasattr(n.creation_time, "timestamp") else None
        out.append({"app": app, "title": texts[0] if texts else app, "body": " ".join(texts[1:]),
                    "time": f"{created:%H:%M}" if created else "", "_ts": created.timestamp() if created else 0})
    out.sort(key=lambda n: n["_ts"], reverse=True)
    return out[: int(cfg.get("max", 10))]
