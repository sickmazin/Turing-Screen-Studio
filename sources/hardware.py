"""Hardware sensors from LibreHardwareMonitorLib (bundled in vendor/lhm, loaded through pythonnet).

CPU temperatures and some motherboard sensors need the app to run as administrator; GPU sensors work anyway.
Data:
  hardware.cpu.{name, load, temp, power, clock}
  hardware.gpu.{name, load, temp, hotspot, memory_temp, mem_load, power, clock, mem_clock, fan, vram_used, vram_total}
  hardware.ram.{load, used, total}      hardware.fans.N.{name, rpm}      hardware.admin
  hardware.sensors["Hardware|Type|Name"] = value   (every sensor, for custom widgets)
"""
import asyncio
import ctypes
import logging
import threading

import paths

name = "hardware"
settings = {}
interval = 2

GPU_ORDER = ("GpuNvidia", "GpuAmd", "GpuIntel")  # prefer a discrete GPU over the Ryzen/Intel integrated one
_computer = None
_lock = threading.Lock()
_error = None


def _open():
    global _computer, _error
    if _computer or _error:
        return _computer
    try:
        import clr  # pythonnet
        lib = paths.VENDOR / "lhm"
        import sys
        sys.path.append(str(lib))
        clr.AddReference(str(lib / "LibreHardwareMonitorLib.dll"))
        from LibreHardwareMonitor.Hardware import Computer
        c = Computer()
        for flag in ("IsCpuEnabled", "IsGpuEnabled", "IsMemoryEnabled", "IsMotherboardEnabled",
                     "IsControllerEnabled", "IsStorageEnabled"):
            setattr(c, flag, True)
        c.Open()
        _computer = c
    except Exception as e:  # library missing or .NET not available: report once, do not retry every 2 s
        _error = repr(e)
        logging.getLogger("studio").warning("hardware sensors unavailable: %s", _error)
    else:
        logging.getLogger("studio").info("hardware sensors ready (administrator: %s)", is_admin())
    return _computer


def _value(v):
    return None if v is None else float(v)


def _sensor(hw, kind, *names):
    """First sensor of the given type whose name matches one of the candidates (in order)."""
    sensors = [s for s in hw.Sensors if str(s.SensorType) == kind and s.Value is not None]
    for n in names:
        for s in sensors:
            if s.Name == n:
                return _value(s.Value)
    return None


def _walk(hw):
    hw.Update()
    yield hw
    for sub in hw.SubHardware:
        yield from _walk(sub)


def read():
    with _lock:
        c = _open()
        if not c:
            return {"error": _error, "admin": is_admin()}
        all_hw = [h for top in c.Hardware for h in _walk(top)]
    out = {"admin": is_admin(), "sensors": {}, "fans": []}
    for h in all_hw:
        for s in h.Sensors:
            if s.Value is not None:
                key = f"{h.Name}|{s.SensorType}|{s.Name}".replace(".", "_")  # dots split field paths
                out["sensors"][key] = round(float(s.Value), 2)
            if str(s.SensorType) == "Fan" and s.Value:
                out["fans"].append({"name": s.Name, "rpm": float(s.Value)})
    cpu = next((h for h in all_hw if str(h.HardwareType) == "Cpu"), None)
    if cpu:
        temp = _sensor(cpu, "Temperature", "Core (Tctl/Tdie)", "CPU Package", "Core Average", "Core (Tctl)")
        out["cpu"] = {"name": str(cpu.Name), "load": _sensor(cpu, "Load", "CPU Total"),
                      "temp": temp or None,  # 0 means "not readable" (no admin rights)
                      "power": _sensor(cpu, "Power", "Package", "CPU Package") or None,
                      "clock": _sensor(cpu, "Clock", "Cores (Average)", "Core #1") or None}
    gpus = sorted((h for h in all_hw if str(h.HardwareType) in GPU_ORDER), key=lambda h: GPU_ORDER.index(str(h.HardwareType)))
    if gpus:
        g = gpus[0]
        used, total = _sensor(g, "SmallData", "GPU Memory Used", "D3D Dedicated Memory Used"), _sensor(g, "SmallData", "GPU Memory Total")
        out["gpu"] = {"name": str(g.Name), "load": _sensor(g, "Load", "GPU Core"), "temp": _sensor(g, "Temperature", "GPU Core"),
                      "hotspot": _sensor(g, "Temperature", "GPU Hot Spot"),
                      "memory_temp": _sensor(g, "Temperature", "GPU Memory Junction", "GPU Memory"),
                      "mem_load": _sensor(g, "Load", "GPU Memory"), "power": _sensor(g, "Power", "GPU Package", "GPU Core"),
                      "clock": _sensor(g, "Clock", "GPU Core"), "mem_clock": _sensor(g, "Clock", "GPU Memory"),
                      "fan": _sensor(g, "Fan", "GPU Fan 1", "GPU Fan"), "vram_used": used, "vram_total": total}
    ram = next((h for h in all_hw if str(h.HardwareType) == "Memory" and "Virtual" not in str(h.Name)), None)
    if ram:
        out["ram"] = {"load": _sensor(ram, "Load", "Memory"), "used": _sensor(ram, "Data", "Memory Used"),
                      "total": None}
        if out["ram"]["used"] is not None:
            avail = _sensor(ram, "Data", "Memory Available")
            out["ram"]["total"] = out["ram"]["used"] + (avail or 0)
    return out


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


async def fetch(cfg):
    return await asyncio.to_thread(read)
