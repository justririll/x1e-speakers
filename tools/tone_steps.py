#!/usr/bin/env python3
"""Per-tone V amplitude of a capture of consecutive tones (3 s each, capture starts 0.5 s late).

usage: tone_steps.py capture.raw f1,f2,... [step_s] [rate]
"""
import math
import struct
import sys


def amp(s, f, sr):
    m = sum(s) / len(s)
    re_ = sum((v - m) * math.cos(2 * math.pi * f * i / sr) for i, v in enumerate(s))
    im = sum((v - m) * math.sin(2 * math.pi * f * i / sr) for i, v in enumerate(s))
    return 2 * math.hypot(re_, im) / len(s)


path, freqs = sys.argv[1], [int(x) for x in sys.argv[2].split(',')]
step = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
sr = int(sys.argv[4]) if len(sys.argv) > 4 else 48000
d = open(path, 'rb').read()
n = len(d) // 8
w = struct.unpack('<%di' % (2 * n), d[:n * 8])
for k, f in enumerate(freqs):
    a0 = int((k * step + 1.5 - 0.5) * sr)   # 1.5 s into each tone
    vals = [amp([s >> 16 for s in w[c::2][a0:a0 + sr // 2]], f, sr) for c in range(2)]
    print(f'{f:5d} Hz: L V {vals[0]:7.1f}   R V {vals[1]:7.1f}')
