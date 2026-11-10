"""Driver for the Turing Smart Screen 3.5" rev. A / UsbMonitor (VID 1A86, PID 5722).

Protocol: 6-byte commands with four 10-bit coordinates, then raw RGB565 little-endian pixels.
Verified on real hardware: a full frame takes ~2 s, a small rectangle ~40 ms.
"""
import time

import serial
from PIL import Image
from serial.tools.list_ports import comports

HELLO, RESET, CLEAR, SCREEN_OFF, SCREEN_ON, BRIGHTNESS, ORIENTATION, BITMAP = 69, 101, 102, 108, 109, 110, 121, 197
ORIENTATIONS = {"portrait": 0, "reverse_portrait": 1, "landscape": 2, "reverse_landscape": 3}
NATIVE = (320, 480)


def pack(cmd, x=0, y=0, ex=0, ey=0) -> bytes:
    """Rev. A command: four 10-bit coordinates packed in 5 bytes, then the command code."""
    return bytes([x >> 2, ((x & 3) << 6) | (y >> 4), ((y & 15) << 4) | (ex >> 6),
                  ((ex & 63) << 2) | (ey >> 8), ey & 255, cmd])


def to_rgb565le(img: Image.Image) -> bytes:
    r, g, b = (bytearray(c.tobytes()) for c in img.convert("RGB").split())
    out = bytearray(len(r) * 2)
    for i in range(len(r)):
        p = ((r[i] & 0xF8) << 8) | ((g[i] & 0xFC) << 3) | (b[i] >> 3)
        out[2 * i], out[2 * i + 1] = p & 0xFF, p >> 8
    return bytes(out)


def find_port():
    for p in comports():
        if p.serial_number == "USB35INCHIPSV2" or (p.vid, p.pid) == (0x1A86, 0x5722):
            return p.device
    return None


class Screen:
    def __init__(self, port="AUTO", orientation="portrait", brightness=40):
        self.port, self.orientation, self.brightness = port, orientation, brightness
        self.ser = None

    @property
    def size(self):
        w, h = NATIVE
        return (h, w) if "landscape" in self.orientation else (w, h)

    def open(self):
        port = find_port() if self.port == "AUTO" else self.port
        if not port:
            raise serial.SerialException("screen not found (VID 1A86 PID 5722)")
        self.ser = serial.Serial(port, 115200, timeout=1, write_timeout=10)
        self.ser.write(bytes([HELLO] * 6))
        self.model = self.ser.read(6)  # 01x6 = UsbMonitor 3.5", empty = original Turing
        self.ser.reset_input_buffer()
        self.set_orientation(self.orientation)
        self.set_brightness(self.brightness)

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            finally:
                self.ser = None

    def set_brightness(self, pct: int):
        self.brightness = max(0, min(100, pct))
        self.ser.write(pack(BRIGHTNESS, int(255 - self.brightness * 2.55)))  # 0 = brightest

    def set_orientation(self, name: str):
        self.orientation = name
        w, h = self.size
        self.ser.write(pack(ORIENTATION) + bytes([ORIENTATIONS[name] + 100, w >> 8, w & 255, h >> 8, h & 255]) + bytes(5))

    def power(self, on: bool):
        self.ser.write(pack(SCREEN_ON if on else SCREEN_OFF))

    def show(self, img: Image.Image, x=0, y=0):
        w, h = img.size
        self.ser.write(pack(BITMAP, x, y, x + w - 1, y + h - 1))
        data = to_rgb565le(img)
        step = self.size[0] * 8
        for i in range(0, len(data), step):
            self.ser.write(data[i:i + step])
