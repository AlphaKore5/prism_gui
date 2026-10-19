"""A QR code for a WhatsApp link, drawn by this file alone (no library to ship).

Byte mode, error correction level M (about one codeword in seven can be wrong and it still reads), versions 1 to 10: up to 213 bytes of
text, which is room for a wa.me link with a greeting. The mask that scores best is used.

    matrix(text)      -> a list of rows of booleans (True = dark), without the quiet zone
    png(matrix, ...)  -> the bytes of a PNG file
    svg(matrix, ...)  -> the text of an SVG file

STDLIB ONLY.
"""
from __future__ import annotations

import struct
import zlib

# (error-correction codewords per block, [(number of blocks, data codewords per block), ...]) at level M
BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)]),
          7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
MAX_VERSION = 10


class QRError(ValueError):
    pass


def capacity(version: int) -> int:
    """How many bytes of text fit at this version."""
    ec, groups = BLOCKS[version]
    data = sum(n * d for n, d in groups)
    return (data * 8 - 4 - (8 if version < 10 else 16)) // 8


def _mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree: int) -> list:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _mul(root, 2)
    return out


def _remainder(data: list, divisor: list) -> list:
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(divisor):
            out[i] ^= _mul(coef, factor)
    return out


def _codewords(data: bytes, version: int) -> list:
    ec_len, groups = BLOCKS[version]
    total_data = sum(n * d for n, d in groups)
    bits = "0100" + format(len(data), "08b" if version < 10 else "016b") + "".join(format(b, "08b") for b in data)
    bits += "0" * min(4, total_data * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    words = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    while len(words) < total_data:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    blocks, at = [], 0
    for n, size in groups:
        for _ in range(n):
            blocks.append(words[at:at + size])
            at += size
    div = _divisor(ec_len)
    ecs = [_remainder(b, div) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(e[i] for e in ecs)
    return out


class _Grid:
    def __init__(self, version: int):
        self.size = version * 4 + 17
        self.version = version
        self.mod = [[False] * self.size for _ in range(self.size)]
        self.fn = [[False] * self.size for _ in range(self.size)]
        self._function_patterns()

    def put(self, x: int, y: int, dark: bool):
        self.mod[y][x] = dark
        self.fn[y][x] = True

    def _function_patterns(self):
        n = self.size
        for i in range(n):
            self.put(6, i, i % 2 == 0)
            self.put(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = ALIGN[self.version]
        for i, cy in enumerate(pos):
            for j, cx in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.put(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)                                    # reserve the format areas (written for real once a mask is chosen)
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = (self.version << 12) | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.put(a, b, bit)
                self.put(b, a, bit)

    def format_bits(self, mask: int):
        n = self.size
        data = (0 << 3) | mask                                 # level M is 00
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = ((data << 10) | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1                   # noqa: E731
        for i in range(6):
            self.put(8, i, bit(i))
        self.put(8, 7, bit(6))
        self.put(8, 8, bit(7))
        self.put(7, 8, bit(8))
        for i in range(9, 15):
            self.put(14 - i, 8, bit(i))
        for i in range(8):
            self.put(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.put(8, n - 15 + i, bit(i))
        self.put(8, n - 8, True)                               # the module that is always dark

    def place(self, words: list):
        n, i = self.size, 0
        total = len(words) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    y = n - 1 - vert if upward else vert
                    if not self.fn[y][x] and i < total:
                        self.mod[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def mask(self, k: int):
        rules = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
                 lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
                 lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)
        for y in range(self.size):
            for x in range(self.size):
                if not self.fn[y][x] and rules[k](x, y):
                    self.mod[y][x] = not self.mod[y][x]

    def penalty(self) -> int:
        n, m, score = self.size, self.mod, 0
        for lines in (m, [list(col) for col in zip(*m)]):
            for row in lines:
                run, prev = 1, row[0]
                for v in row[1:]:
                    if v == prev:
                        run += 1
                        continue
                    if run >= 5:
                        score += 3 + run - 5
                    run, prev = 1, v
                if run >= 5:
                    score += 3 + run - 5
                text = "".join("1" if v else "0" for v in row)
                for pat in ("10111010000", "00001011101"):
                    at = text.find(pat)
                    while at >= 0:
                        score += 40
                        at = text.find(pat, at + 1)
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(1 for v in row if v) for row in m)
        total = n * n
        score += (-(-abs(dark * 20 - total * 10) // total) - 1) * 10
        return score


def matrix(text: str, *, version: int = 0) -> list:
    """The QR code for `text` as rows of booleans. Raises QRError if it is too long for version 10."""
    data = text.encode("utf-8")
    versions = [version] if version else range(1, MAX_VERSION + 1)
    chosen = next((v for v in versions if len(data) <= capacity(v)), None)
    if chosen is None:
        raise QRError("That link is too long for a QR code (%d bytes; the most is %d). Shorten the greeting." % (len(data), capacity(MAX_VERSION)))
    words = _codewords(data, chosen)
    best = None
    for k in range(8):
        g = _Grid(chosen)
        g.place(words)
        g.mask(k)
        g.format_bits(k)
        p = g.penalty()
        if best is None or p < best[0]:
            best = (p, g)
    return [list(row) for row in best[1].mod]


def png(m: list, scale: int = 8, border: int = 4) -> bytes:
    """A black-and-white PNG of the code with a quiet zone of `border` modules."""
    n = len(m) + 2 * border
    rows = []
    for y in range(n):
        line = bytearray()
        for x in range(n):
            dark = border <= x < n - border and border <= y < n - border and m[y - border][x - border]
            line.extend(b"\x00" if dark else b"\xff")
        rows.append(b"\x00" + bytes(line) * 1)
    # scale up: repeat each pixel `scale` times across and down
    out = []
    for r in rows:
        body = r[1:]
        wide = b"".join(body[i:i + 1] * scale for i in range(len(body)))
        out.extend([b"\x00" + wide] * scale)
    size = n * scale

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(out), 9)) + chunk(b"IEND", b"")


def svg(m: list, scale: int = 8, border: int = 4, dark: str = "#000000", light: str = "#ffffff") -> str:
    n = len(m) + 2 * border
    cells = "".join("M%d,%dh1v1h-1z" % (x + border, y + border) for y, row in enumerate(m) for x, v in enumerate(row) if v)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" shape-rendering="crispEdges">'
            '<rect width="100%%" height="100%%" fill="%s"/><path d="%s" fill="%s"/></svg>\n' % (n, n, n * scale, n * scale, light, cells, dark))
