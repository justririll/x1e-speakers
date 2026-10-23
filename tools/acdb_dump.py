#!/usr/bin/env python3
"""Minimal AudioReach ACDB (acdb_cal.acdb) parser.

Layout follows AudioReach/audioreach-graphservices acdb/ (acdb_parser.h,
acdb_types.h, acdb_command.c). Dumps subgraph->module maps and calibration
payloads (CSLU -> CAKT/CDLU -> CDDE/CDDO -> POOL).
"""
import argparse
import json
import struct
import sys

SP_MODULES = {
    0x070010E2: 'SPEAKER_PROTECTION (RX, SPv5 legacy id)',
    0x070010E3: 'SPEAKER_PROTECTION_VI (SPv5 legacy id)',
    0x070010E4: 'SP related (0x070010E4, unknown)',
    0x0701000F: 'SPEAKER_PROTECTION_V7 (RX)',
    0x0702C003: 'SPEAKER_PROTECTION_V7_VI',
    0x07001180: 'CPS_DATA_ROUTER_V7',
    0x070010E5: 'HAPTICS_VI',
}


def u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def u32s(d, o, n):
    return list(struct.unpack_from(f'<{n}I', d, o))


class Acdb:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        assert self.d[:4] == b'ACDB', 'not an ACDB file'
        self.chunks = {}
        off = 12
        while off + 8 <= len(self.d):
            tag = self.d[off:off + 4].decode('latin1')
            size = u32(self.d, off + 4)
            self.chunks[tag] = (off + 8, size)
            off += 8 + size

    def chunk(self, tag):
        return self.chunks[tag]

    def sg_modules(self):
        """SGIT: <sg_id, proc_count, size> then per proc <proc_id, count, [mid, iid]...>"""
        base, size = self.chunk('SGIT')
        d = self.d
        o = base
        n = u32(d, o); o += 4
        out = {}
        for _ in range(n):
            sg, nproc, sz = u32s(d, o, 3); o += 12
            end = o + sz
            mods = []
            p = o
            while p < end:
                proc, cnt = u32s(d, p, 2); p += 8
                for _ in range(cnt):
                    mid, iid = u32s(d, p, 2); p += 8
                    mods.append({'proc': proc, 'mid': mid, 'iid': iid})
            out[sg] = mods
            o = end
        return out

    def pool(self, off):
        base, _ = self.chunk('POOL')
        size = u32(self.d, base + off)
        return self.d[base + off + 4: base + off + 4 + size]

    def caldata(self):
        """Yield (sg, ckv_keys, ckv_values, iid, pid, payload)."""
        d = self.d
        cslu, _ = self.chunk('CSLU')
        cakt, _ = self.chunk('CAKT')
        cdlu, _ = self.chunk('CDLU')
        cdde, _ = self.chunk('CDDE')
        cddo, _ = self.chunk('CDDO')
        o = cslu
        nsg = u32(d, o); o += 4
        for _ in range(nsg):
            sg, nckv = u32s(d, o, 2); o += 8
            for _ in range(nckv):
                off_key, off_lut = u32s(d, o, 2); o += 8
                k = cakt + off_key
                nkeys = u32(d, k)
                keys = u32s(d, k + 4, nkeys)
                l = cdlu + off_lut
                lut_nkeys, nent = u32s(d, l, 2); l += 8
                for _ in range(nent):
                    vals = u32s(d, l, nkeys); l += 4 * nkeys
                    off_def, off_dot, off_dot2 = u32s(d, l, 3); l += 12
                    de = cdde + off_def
                    npairs = u32(d, de); de += 4
                    do = cddo + off_dot + 4
                    for _ in range(npairs):
                        iid, pid = u32s(d, de, 2); de += 8
                        poff = u32(d, do); do += 4
                        yield sg, keys, vals, iid, pid, self.pool(poff)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('acdb')
    ap.add_argument('--all', action='store_true', help='dump all modules, not only SP')
    ap.add_argument('--json', help='write extracted SP params to this JSON file')
    a = ap.parse_args()

    db = Acdb(a.acdb)
    sgm = db.sg_modules()
    iid2mod = {}
    for sg, mods in sgm.items():
        for m in mods:
            iid2mod[m['iid']] = m['mid']

    print(f'# {len(sgm)} subgraphs')
    for sg, mods in sorted(sgm.items()):
        hit = [m for m in mods if m['mid'] in SP_MODULES]
        if a.all or hit:
            print(f'SG {sg:#010x}:')
            for m in mods:
                tag = SP_MODULES.get(m['mid'], '')
                print(f'   proc={m["proc"]} mid={m["mid"]:#010x} iid={m["iid"]:#06x} {tag}')

    sp_iids = {i for i, m in iid2mod.items() if m in SP_MODULES}
    out = []
    print('\n# calibration for SP modules')
    for sg, keys, vals, iid, pid, payload in db.caldata():
        if not a.all and iid not in sp_iids:
            continue
        ckv = ','.join(f'{k:#x}={v:#x}' for k, v in zip(keys, vals))
        mid = iid2mod.get(iid, 0)
        print(f'SG {sg:#010x} CKV[{ckv}] iid={iid:#06x} mid={mid:#010x} pid={pid:#010x} len={len(payload)}')
        print('   ' + payload.hex(' ', 4))
        out.append({'sg': sg, 'ckv': dict(zip(keys, vals)), 'iid': iid, 'mid': mid,
                    'pid': pid, 'data': payload.hex()})
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    sys.exit(main())
