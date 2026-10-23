#!/usr/bin/env python3
"""Decode known Speaker Protection VI params from sp_params.json (acdb_dump.py output).

Struct layouts from AudioReach spf/api/modules/sp_vi.h. Legacy (SPv5) PIDs found
in the X1E ACDB are mapped onto the public struct definitions by size/layout.
"""
import json
import struct
import sys


def q(v, n):
    return v / float(1 << n)


def static_cfg(b):
    f = struct.unpack('<11I', b)
    names = ['num_speakers', 'sampling_rate', 'fpilot', 'th_ctrl_rate', 'th_frame_size_ms',
             'th_pow_supply_freq', 'th_temp_est_selection_flag', 'ex_frame_size',
             'ex_tuning_mode_enable_flag', 'ex_DC_detection_enable_flag', 'ex_warmup_time_ms']
    return dict(zip(names, f))


def th_dynamic(b):
    n, = struct.unpack_from('<I', b, 0)
    o = 4
    spk = []
    for _ in range(n):
        (r0_safe, pilot, trace, r_typ, r_fac, v_fs, resist, dtdr, t0_safe,
         vsen, isen, vpilot, _res) = struct.unpack_from('<iIihhhHHhHHHh', b, o)
        o += 32
        spk.append({
            'r0_safe_ohm': round(q(r0_safe, 24), 4),
            'pilot_tone_scale_q18': pilot,
            'trace_resistance_ohm': round(q(trace, 24), 4),
            'r_spk_coil_typ_ohm': round(q(r_typ, 8), 3),
            'r_spk_coil_open_factor': q(r_fac, 10),
            'v_full_scale_V': round(q(v_fs, 10), 3),
            'resistivity_coeff_inv_alpha': round(q(resist, 7), 2),
            'dT_dR_ratio_raw': hex(dtdr),
            't0_safe_C': q(t0_safe, 6),
            'vsen_2_v_q11': round(q(vsen, 11), 4),
            'isen_2_a_q11': round(q(isen, 11), 4),
            'v_pilot_thsd': round(q(vpilot, 16), 3),
        })
    for s in spk:
        wait, cali, viwait, und, rng, tmin, tmax = struct.unpack_from('<iiiHhhh', b, o)
        o += 20
        s['cali'] = {'wait_time_ms': wait, 'cali_time_ms': cali, 'vi_wait_time_ms': viwait,
                     'r0_under_est_fac': round(q(und, 16), 3), 'r0_range_fac': q(rng, 10),
                     't0_min_C': q(tmin, 6), 't0_max_C': q(tmax, 6)}
    assert o == len(b), (o, len(b))
    return {'num_ch': n, 'speakers': spk}


def max_rated_temp(b):
    n, = struct.unpack_from('<I', b, 0)
    return {'num_ch': n, 'temp_rated_C': [q(t, 6) for t in struct.unpack_from(f'<{n}i', b, 4)]}


def chan_map(b):
    n, = struct.unpack_from('<I', b, 0)
    return {'num_ch': n, 'map': list(struct.unpack_from(f'<{n}I', b, 4))}


DECODERS = {
    0x080011F6: ('SP_VI_STATIC_CFG', static_cfg),
    0x08001535: ('TH_VI_DYNAMIC_CFG (legacy pid)', th_dynamic),
    0x08001510: ('MAX_RATED_TEMP', max_rated_temp),
    0x08001203: ('SP_VI_CHANNEL_MAP_CFG', chan_map),
}


def main():
    for e in json.load(open(sys.argv[1])):
        dec = DECODERS.get(e['pid'])
        if not dec:
            continue
        name, fn = dec
        print(f'== iid={e["iid"]:#x} pid={e["pid"]:#x} {name}')
        print(json.dumps(fn(bytes.fromhex(e['data'])), indent=2))


if __name__ == '__main__':
    main()
