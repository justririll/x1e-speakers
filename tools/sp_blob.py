#!/usr/bin/env python3
"""Build AudioReach topology module config blobs (SND_SOC_AR_TPLG_MODULE_CFG_TYPE) for the
speaker protection RX / VI modules from the Windows ACDB values (sp_params.json).

usage: sp_blob.py sp_params.json RX_IID VI_IID [--ftm] [--vi-map a,b,c,d] [--temp-tgt C] [--xmax MM] > sp_cfg.m4

--ftm: test build, puts RX and VI into factory test mode (VI measures speaker R and
temperature, read back with PARAM_ID_SP_TH_VI_FTM_PARAMS 0x080011FA).
--temp-tgt: test build, thermal target temperature (vendor: 80 C) to check that the
protection reacts to heating without heating the coils to 80 C.
--xmax: test build, maximum excursion in mm (vendor: 0.4) to check that the excursion
protection reacts at a low level.
--vi-map: send PARAM_ID_SP_VI_CHANNEL_MAP_CFG with this order (overrides the kernel's 1,2,3,4).

The blob is a list of APM_CMD_SET_CFG params ({iid, param_id, size, error} + payload padded
to 8 bytes) behind a 16-byte header {size incl. header, type, priv[2]}. The m4 output defines
SP_RX_CFG_BYTES / SP_VI_CFG_BYTES for SectionData bytes.

Params the kernel sends itself (MODULE_ENABLE, VI CHANNEL_MAP) and unknown generic ones are
skipped. Adjusted for the Linux graph: RX input is 16-bit, VI runs at 48 kHz (an 8 kHz VI
stream on the SoundWire bus next to 48 kHz playback gave bus clash / parity errors).
"""
import json
import struct
import sys

MODULE_CFG_TYPE = 0x01001006
WIN_RX_IID, WIN_VI_IID = 0x411A, 0x4121
SKIP = {
    0x08001026,  # PARAM_ID_MODULE_ENABLE (kernel)
    0x08001203,  # PARAM_ID_SP_VI_CHANNEL_MAP_CFG (kernel)
    0x080010A6,  # unknown generic param, same in every module
}
SP_STATIC_CFG = 0x080011E8      # RX: sampling_rate, bits_per_sample, ...
SP_VI_STATIC_CFG = 0x080011F6   # VI: num_speakers, vi_sampling_rate, ...


SP_DYNAMIC_CFG = 0x08001532         # RX: th_ctrl[ch].temp_tgt_q6 at 312 + 40 * ch
TEMP_TGT_OFF = (312, 352)
XMAX_OFF = (376, 688)               # RX: ex_ctrl[ch].max_excursion_mm_q27


def patch(pid, data):
    b = bytearray(data)
    if pid == SP_DYNAMIC_CFG and '--temp-tgt' in sys.argv:
        tgt = float(sys.argv[sys.argv.index('--temp-tgt') + 1])
        for o in TEMP_TGT_OFF:
            assert struct.unpack_from('<i', b, o)[0] == 80 * 64
            struct.pack_into('<i', b, o, round(tgt * 64))
    if pid == SP_DYNAMIC_CFG and '--xmax' in sys.argv:
        xmax = float(sys.argv[sys.argv.index('--xmax') + 1])
        for o in XMAX_OFF:
            assert abs(struct.unpack_from('<i', b, o)[0] / 2**27 - 0.4) < 1e-6
            struct.pack_into('<i', b, o, round(xmax * 2**27))
    if pid == SP_STATIC_CFG:
        struct.pack_into('<I', b, 4, 16)
    elif pid == SP_VI_STATIC_CFG:
        struct.pack_into('<I', b, 4, 48000)
    return bytes(b)


def blob(params, iid):
    body = b''
    for pid, data in params:
        body += struct.pack('<IIII', iid, pid, len(data), 0) + data
        body += b'\0' * (-len(data) % 8)
    return struct.pack('<IIII', 16 + len(body), MODULE_CFG_TYPE, 0, 0) + body


def m4_bytes(name, b):
    return "define(`%s', `%s') dnl\n" % (name, ','.join('0x%02x' % x for x in b))


SP_TH_VI_R0T0_CFG = 0x080011F5     # VI: num_ch, {r0_cali_q24, t0_cali_q6, reserved}[n]
R0_SAFE = (7.345, 7.567)           # Ohm, left/right (SP_TH_VI_DYNAMIC_CFG r0_safe)
T0_SAFE = 25.0                     # deg C
SP_OP_MODE_V5 = 0x080011E9         # RX: operation_mode
SP_VI_OP_MODE_CFG = 0x080011F4     # VI: num_speakers, th_operation_mode, quick_calib, r0t0_sel[n]
SP_TH_VI_FTM_CFG = 0x080011F9      # VI: num_ch, {wait_time_ms, ftm_time_ms}[n]
OP_MODE_FTM = 2


def ftm_params():
    rx = [(SP_OP_MODE_V5, struct.pack('<I', OP_MODE_FTM))]
    vi = [(SP_VI_OP_MODE_CFG, struct.pack('<5I', 2, OP_MODE_FTM, 0, 0, 0)),
          (SP_TH_VI_FTM_CFG, struct.pack('<5I', 2, 1000, 2000, 1000, 2000))]
    return rx, vi


def main():
    entries = json.load(open(sys.argv[1]))
    rx_iid, vi_iid = int(sys.argv[2], 0), int(sys.argv[3], 0)
    out = {WIN_RX_IID: [], WIN_VI_IID: []}
    for e in entries:
        if e['iid'] in out and e['pid'] not in SKIP:
            out[e['iid']].append((e['pid'], patch(e['pid'], bytes.fromhex(e['data']))))
    # R0/T0 reference of the coils. The kernel selects "calibrated" R0/T0 and the ACDB has
    # none (the vendor driver sets them at runtime); without them the module uses 2.0 Ohm and
    # sees a hot coil. Use the safe values of SP_TH_VI_DYNAMIC_CFG (no per-unit calibration).
    out[WIN_VI_IID].append((SP_TH_VI_R0T0_CFG, struct.pack('<I' + 'ihh' * len(R0_SAFE), len(R0_SAFE),
        *[v for r0 in R0_SAFE for v in (round(r0 * (1 << 24)), round(T0_SAFE * (1 << 6)), 0)])))
    if '--vi-map' in sys.argv:
        m = [int(x) for x in sys.argv[sys.argv.index('--vi-map') + 1].split(',')]
        out[WIN_VI_IID].append((0x08001203, struct.pack('<%dI' % (len(m) + 1), len(m), *m)))
    if '--ftm' in sys.argv:
        frx, fvi = ftm_params()
        out[WIN_RX_IID] += frx
        out[WIN_VI_IID] += fvi
    rx, vi = blob(out[WIN_RX_IID], rx_iid), blob(out[WIN_VI_IID], vi_iid)
    sys.stdout.write('dnl generated by tools/sp_blob.py from the Windows ACDB, do not edit\n')
    sys.stdout.write(m4_bytes('SP_RX_CFG_BYTES', rx))
    sys.stdout.write(m4_bytes('SP_VI_CFG_BYTES', vi))
    sys.stderr.write('RX %d params %d bytes, VI %d params %d bytes\n'
                     % (len(out[WIN_RX_IID]), len(rx), len(out[WIN_VI_IID]), len(vi)))


if __name__ == '__main__':
    main()
