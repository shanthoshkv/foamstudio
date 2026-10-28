"""Tiny PNG writer and mean absolute difference. Used when VTK is not on screen."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def write_png(path: Path, rgb: list[list[tuple[int, int, int]]]) -> None:
    if not rgb or not rgb[0]:
        raise ValueError("The image has no pixels.")
    height = len(rgb)
    width = len(rgb[0])
    raw = bytearray()
    for row in rgb:
        if len(row) != width:
            raise ValueError("PNG rows must be the same width.")
        raw.append(0)
        for red, green, blue in row:
            raw.extend((red & 255, green & 255, blue & 255))
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def read_rgb(path: Path) -> list[list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG.")
    offset = 8
    width = height = None
    compressed = b""
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        tag = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if tag == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
        elif tag == b"IDAT":
            compressed += payload
        elif tag == b"IEND":
            break
    if width is None or height is None:
        raise ValueError(f"{path} has no IHDR.")
    raw = zlib.decompress(compressed)
    rows: list[list[tuple[int, int, int]]] = []
    stride = 1 + width * 3
    for y in range(height):
        start = y * stride
        row = raw[start + 1 : start + stride]
        rows.append([(row[i], row[i + 1], row[i + 2]) for i in range(0, len(row), 3)])
    return rows


def mean_abs_diff(left: Path, right: Path) -> float:
    a = read_rgb(left)
    b = read_rgb(right)
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        raise ValueError("Images differ in size, so they cannot be compared.")
    total = 0
    count = 0
    for row_a, row_b in zip(a, b, strict=True):
        for pixel_a, pixel_b in zip(row_a, row_b, strict=True):
            total += sum(
                abs(channel_a - channel_b)
                for channel_a, channel_b in zip(pixel_a, pixel_b, strict=True)
            )
            count += 3
    return total / count if count else 0.0
