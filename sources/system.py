import time

import psutil

name = "system"
settings = {"disk": "C:\\"}  # defaults, editable in the Data tab
interval = 1

_last_net = None


async def fetch(cfg):
    global _last_net
    net = psutil.net_io_counters()
    now = time.monotonic()
    down = up = 0.0
    if _last_net:
        dt = now - _last_net[0]
        down = (net.bytes_recv - _last_net[1].bytes_recv) / dt
        up = (net.bytes_sent - _last_net[1].bytes_sent) / dt
    _last_net = (now, net)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(cfg.get("disk", "C:\\"))
    return {
        "cpu": psutil.cpu_percent(),
        "cores": psutil.cpu_percent(percpu=True),
        "ram": mem.percent, "ram_used": mem.used, "ram_total": mem.total,
        "disk": disk.percent,
        "down": down, "up": up,
        "uptime": time.time() - psutil.boot_time(),
    }
