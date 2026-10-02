"""
luma_input.py

Minimal Python client for Luma3DS's Rosalina "Input Redirection" feature --
the same UDP protocol used by InputRedirectionClient-Qt (TuxSH) and TPPFLUSH
(hlixed). Sends 20-byte state packets over UDP port 4950.

Enable it on-console first: Rosalina menu (L+Down+Select) ->
Miscellaneous options -> Enable InputRedirection. The 3DS's IP address is
shown on that screen.

This is an independent re-implementation of the wire format documented by
TuxSH/Stary2001 and packaged as TPPFLUSH by hlixed -- credit to them for
reverse-engineering the protocol in the first place.
"""

import socket
import time
from enum import IntFlag, auto

PORT = 4950


class Button(IntFlag):
    A = auto()
    B = auto()
    SELECT = auto()
    START = auto()
    RIGHT = auto()
    LEFT = auto()
    UP = auto()
    DOWN = auto()
    R = auto()
    L = auto()
    X = auto()
    Y = auto()


class N3DSInput(IntFlag):
    ZL = 2
    ZR = 4


class SpecialButton(IntFlag):
    HOME = auto()
    POWER = auto()
    POWER_LONG = auto()


def _invert(b: bytearray) -> bytearray:
    return bytearray(255 - x for x in b)


class Luma3DSInput:
    """One instance per 3DS. Call .send() after changing state -- nothing
    happens on the console until you do. .tap() does press/send/wait/
    release/send for you, which is what most of this project uses."""

    CPAD_BOUND = 0x5D0
    CSTICK_BOUND = 0x7F
    SQRT_HALF = 0.70710678118654752440
    TOUCH_W, TOUCH_H = 320, 240

    def __init__(self, ip: str, port: int = PORT):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect((ip, port))
        self.buttons = Button(0)
        self.n3ds = N3DSInput(0)
        self.special = SpecialButton(0)
        self.cpad = [0.0, 0.0]
        self.cstick = [0.0, 0.0]
        self.touch = None  # None = not touching, else (x, y)

    # -- state helpers -----------------------------------------------
    def press(self, *buttons: Button):
        for b in buttons:
            self.buttons |= b

    def release(self, *buttons: Button):
        for b in buttons:
            self.buttons &= ~b

    def release_all(self):
        self.buttons = Button(0)
        self.n3ds = N3DSInput(0)
        self.special = SpecialButton(0)
        self.cpad = [0.0, 0.0]
        self.cstick = [0.0, 0.0]
        self.touch = None

    def set_circle_pad(self, x: float, y: float):
        """x, y each in [-1, 1]."""
        self.cpad = [max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))]

    def set_touch(self, x: int, y: int):
        self.touch = (max(0, min(self.TOUCH_W - 1, x)),
                      max(0, min(self.TOUCH_H - 1, y)))

    def clear_touch(self):
        self.touch = None

    # -- wire format ---------------------------------------------------
    def send(self):
        hid_bytes = int(self.buttons).to_bytes(4, "little")
        hid_state = _invert(bytearray(hid_bytes))

        touch_state = bytearray.fromhex("20000000")
        if self.touch is not None:
            x, y = self.touch
            tx = (x * 4096) // self.TOUCH_W
            ty = (y * 4096) // self.TOUCH_H
            touch_state = (tx | (ty << 12) | (0x01 << 24)).to_bytes(4, "little")

        circle_state = bytearray.fromhex("00088000")
        if self.cpad != [0.0, 0.0]:
            cx = int(self.cpad[0] * 32767)
            cy = int(self.cpad[1] * 32767)
            x = ((cx * self.CPAD_BOUND) // 32768) + 2048
            y = ((cy * self.CPAD_BOUND) // 32768) + 2048
            circle_state = (x | (y << 12)).to_bytes(4, "little")

        n3ds_state = bytearray.fromhex("81008080")
        if self.cstick != [0.0, 0.0] or int(self.n3ds) != 0:
            x, y = self.cstick
            # 45-degree rotation of the c-stick position -- per TuxSH's
            # reverse-engineering notes ("thanks, Nintendo").
            rx = int(((x + y) * self.SQRT_HALF * self.CSTICK_BOUND) + 0x80)
            ry = int(((y - x) * self.SQRT_HALF * self.CSTICK_BOUND) + 0x80)
            n3ds_state = (
                (ry & 0xFF) << 24 | (rx & 0xFF) << 16 |
                (int(self.n3ds) & 0xFF) << 8 | 0x81
            ).to_bytes(4, "little")

        special_bytes = int(self.special).to_bytes(4, "little")

        packet = bytearray(20)
        packet[0:4] = hid_state
        packet[4:8] = touch_state
        packet[8:12] = circle_state
        packet[12:16] = n3ds_state
        packet[16:20] = special_bytes
        self.sock.send(packet)

    def tap(self, *buttons: Button, hold: float = 0.08, gap: float = 0.12,
            resend: int = 3):
        """Press, hold `hold` seconds, release, then wait `gap` seconds.
        Since InputRedirection runs over UDP (no delivery guarantee, and
        this is going over Wi-Fi), a single dropped packet can silently
        skip a press. Resending the pressed-state packet a few times
        across the hold window makes that far less likely without
        changing the effective timing."""
        self.press(*buttons)
        step = hold / resend if resend > 0 else hold
        for _ in range(max(1, resend)):
            self.send()
            time.sleep(step)
        self.release(*buttons)
        for _ in range(max(1, resend)):
            self.send()
            time.sleep(gap / resend if resend > 0 else gap)

    def return_control(self):
        """Hand control back to the physical console buttons."""
        self.sock.send(bytearray.fromhex(
            "ff0f000000000002fff77f008100808000000000"))

    def close(self):
        try:
            self.release_all()
            self.send()
            self.return_control()
        finally:
            self.sock.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python luma_input.py <3ds ip>  (taps A once, as a connectivity test)")
        sys.exit(1)
    pad = Luma3DSInput(sys.argv[1])
    pad.tap(Button.A)
    pad.close()
    print("Sent an A press. If nothing happened on-console, double check "
          "the IP and that InputRedirection is enabled in Rosalina.")
