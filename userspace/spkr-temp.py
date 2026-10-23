# Live speaker coil temperature estimate from the V/I feedback probe of spkr-vi-feedback.
#
# usage: spkr-temp [interval_s]
#
# The service writes a 50 ms V/I probe (S32_LE, 2 ch, V hi16 | I lo16) to /run/spkr-vi-probe.raw
# every second. R = <V*I>/<I*I> in raw counts, relative to a cold reference measured on this unit
# with a 1 kHz tone (music gives a somewhat higher R: the speaker impedance depends on frequency).
# A rough estimate: the DSP measures the coil itself and is what limits it.
# dT = (R/R0 - 1) / alpha_Cu. The DSP protection limits the coil to 80 C.
import math
import os
import struct
import sys
import time

PROBE = '/run/spkr-vi-probe.raw'
MUTED = '/var/lib/spkr-vi-feedback/volume'
REF = (1.2310, 1.2827)      # cold R in counts (L, R), 1 kHz -30 dBFS, 2026-10-23
R0 = (7.345, 7.567)         # Ohm, safe R0 of the topology at T0
T0 = 25.0
T_MAX = 80.0
ALPHA_CU = 0.0039
FULL_SCALE_V = 13.64
AVG = 5                     # probes averaged for R
MIN_V_COUNTS = 0.6 / FULL_SCALE_V * 32768


def probe():
    try:
        st = os.stat(PROBE)
        d = open(PROBE, 'rb').read()
    except OSError:
        return None, None
    n = len(d) // 8
    if not n:
        return None, st.st_mtime
    w = struct.unpack('<%di' % (2 * n), d[:n * 8])
    out = []
    for c in range(2):
        x = w[c::2]
        v = [s >> 16 for s in x]
        i = [((s & 0xffff) ^ 0x8000) - 0x8000 for s in x]
        mv, mi = sum(v) / n, sum(i) / n
        v = [a - mv for a in v]
        i = [b - mi for b in i]
        vi, ii, vv = sum(a * b for a, b in zip(v, i)), sum(b * b for b in i), sum(a * a for a in v)
        # Only loud enough probes (V rms > ~0.6 V): on pauses and quiet passages noise and the
        # speaker impedance away from DC make R jump (seen: 0.2 V fade-out -> "+70 K" in 3 s)
        ok = vv / n > MIN_V_COUNTS ** 2 and vi > 0.8 * math.sqrt(ii * vv)
        out.append((vi, ii, vv / n, ok))
    nodata = all(s & 0xffffffff in (0x80008000, 0) for s in w)
    return (None if nodata else out), st.st_mtime


def main():
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    hist = [[], []]
    last = None
    print('        |        left                     |        right                    |')
    print('  time  | R/R0   dT     T      V rms      | R/R0   dT     T      V rms      | state')
    while True:
        p, mtime = probe()
        if os.path.exists(MUTED):
            state = 'MUTED: no V/I feedback'
        elif mtime is None or time.time() - mtime > 3:
            state = 'idle (speakers off)'
        elif p is None:
            state = 'NO V/I DATA'
        else:
            state = 'ok'
        cols = []
        for c in range(2):
            if state == 'ok' and mtime != last:
                vi, ii, vv, ok = p[c]
                if ok:
                    hist[c] = (hist[c] + [(vi, ii)])[-AVG:]
            if state == 'ok' and hist[c]:
                q = sum(a for a, b in hist[c]) / sum(b for a, b in hist[c]) / REF[c]
                dt = (q - 1) / ALPHA_CU
                vrms = math.sqrt(p[c][2]) / 32768 * FULL_SCALE_V
                warn = ' HOT' if T0 + dt > T_MAX - 10 else '    '
                cols.append('%5.3f %+5.0fK %4.0fC %5.2f V%s' % (q, dt, T0 + dt, vrms, warn))
            else:
                cols.append('%-31s' % ('  -'))
        last = mtime
        print('%s | %s | %s | %s' % (time.strftime('%H:%M:%S'), cols[0], cols[1], state), flush=True)
        time.sleep(interval)


try:
    main()
except KeyboardInterrupt:
    pass
