#!/usr/bin/env python3
"""Coil temperature rise and output level over time from a V/I feedback capture.

usage: heat_analyze.py capture.raw [window_s] [ref_s] [rate]

capture.raw: S32_LE, 2 ch (left, right), rate Hz (default 48000); each sample = V (bits 31..16) | I (15..0).
Per window: R = <V*I>/<I*I> (raw counts, proportional to the coil resistance at the signal's
frequencies), dT = (R/R_ref - 1) / alpha with R_ref = mean R over the first ref_s seconds,
and V rms in dBFS of the 16-bit V sense (shows gain reduction by speaker protection).
"""
import math
import struct
import sys

ALPHA_CU = 0.0039  # 1/K


def windows(path, win_s, rate):
    d = open(path, 'rb').read()
    n = len(d) // 8
    w = struct.unpack('<%di' % (2 * n), d[:n * 8])
    step = int(win_s * rate)
    for k in range(0, n // step):
        yield k * win_s, [w[c::2][k * step:(k + 1) * step] for c in range(2)]


def stats(x):
    v = [s >> 16 for s in x]
    i = [((s & 0xffff) ^ 0x8000) - 0x8000 for s in x]
    mv, mi = sum(v) / len(v), sum(i) / len(i)
    v = [a - mv for a in v]
    i = [a - mi for a in i]
    vi = sum(a * b for a, b in zip(v, i))
    ii = sum(b * b for b in i)
    vrms = math.sqrt(sum(a * a for a in v) / len(v))
    irms = math.sqrt(ii / len(i))
    return (vi / ii if ii else float('nan')), vrms, irms


def main():
    path = sys.argv[1]
    win = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    ref_s = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    rate = int(sys.argv[4]) if len(sys.argv) > 4 else 48000
    rows = [(t, [stats(ch) for ch in chans]) for t, chans in windows(path, win, rate)]
    ref = []
    for c in range(2):
        r = [s[c][0] for t, s in rows if t < ref_s and s[c][2] > 20]
        ref.append(sum(r) / len(r) if r else float('nan'))
    print(f'R_ref (counts): L {ref[0]:.4f}  R {ref[1]:.4f}')
    print('   t   | L: R/Rref   dT   Vrms dBFS | R: R/Rref   dT   Vrms dBFS')
    for t, s in rows:
        out = []
        for c in range(2):
            r, vrms, irms = s[c]
            if irms > 20:
                q = r / ref[c]
                out.append(f'{q:7.4f} {(q - 1) / ALPHA_CU:6.1f} {20 * math.log10(vrms / 32768 + 1e-12):7.1f}')
            else:
                out.append('   (quiet)' + ' ' * 15)
        print(f'{t:6.1f} | ' + ' | '.join(out))


if __name__ == '__main__':
    main()
