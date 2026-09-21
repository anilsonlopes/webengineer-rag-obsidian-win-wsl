"""Generate the small application icon from geometric shapes; no image dependencies."""
from pathlib import Path
import struct

size = 64
pixels = bytearray()
for y in reversed(range(size)):
    for x in range(size):
        color = (24, 42, 57, 255)
        if 12 <= x <= 41 and 12 <= y <= 49:
            color = (229, 240, 243, 255)
        if 17 <= x <= 35 and (19 <= y <= 21 or 27 <= y <= 29 or 35 <= y <= 37):
            color = (24, 42, 57, 255)
        distance = (x - 43) ** 2 + (y - 39) ** 2
        if 49 <= distance <= 100 or (47 <= x <= 57 and abs((y - 45) - (x - 47)) <= 2):
            color = (42, 194, 173, 255)
        r, g, b, a = color
        pixels.extend((b, g, r, a))
mask = bytes(((size + 31) // 32) * 4 * size)
header = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
image = header + pixels + mask
ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(image), 22) + image
(Path(__file__).resolve().parents[1] / "packaging" / "icon.ico").write_bytes(ico)
