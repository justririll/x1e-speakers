#!/usr/bin/env python3
"""Decode legacy (SPv5) Speaker Protection RX/VI params from sp_params.json.

Legacy PID -> public struct mapping was established by payload size/layout
against AudioReach spf/api/modules/sp_rx.h and sp_vi.h (sizes from gcc sizeof).
"""
import json
import struct
import sys


def q(v, n):
    return round(v / float(1 << n), 6)


def qname(name, v):
    """Scale by the _qNN suffix of a field name, if present."""
    for part in reversed(name.split('_')):
        if part.startswith('q') and part[1:].isdigit():
            return q(v, int(part[1:]))
        if part.startswith('dBq') and part[3:].isdigit():
            return q(v, int(part[3:]))
        if part.startswith('u16q') and part[4:].isdigit():
            return q(v, int(part[4:]))
    return v


def fields(names, b, off=0, fmt='i'):
    vals = struct.unpack_from(f'<{len(names)}{fmt}', b, off)
    return {n: qname(n, v) for n, v in zip(names, vals)}, off + 4 * len(names)


def tdf2(b, off):
    nch, stages = struct.unpack_from('<hh', b, off)
    num = struct.unpack_from('<15i', b, off + 4)
    den = struct.unpack_from('<10i', b, off + 64)
    numq = struct.unpack_from('<5h', b, off + 104)
    denq = struct.unpack_from('<5h', b, off + 114)
    return {'numCh': nch, 'stages': stages, 'num': num[:3 * stages], 'den': den[:2 * stages],
            'numQ': numq[:stages], 'denQ': denq[:stages]}, off + 124


def nch_filt(b, off):
    num = struct.unpack_from('<15i', b, off)
    den = struct.unpack_from('<10i', b, off + 60)
    numq = struct.unpack_from('<5h', b, off + 100)
    denq = struct.unpack_from('<5h', b, off + 110)
    return {'num': num, 'den': den, 'num_q': numq, 'den_q': denq}, off + 120


def static_cfg(b):
    names = ['sampling_rate', 'bits_per_sample', 'num_speakers', 'frame_size_ms', 'features',
             'tuning_mode_en_flag', 'ctrl_rate', 'num_nch_filter_stages']
    out, o = fields(names, b, 0, 'I')
    t, p, lvl, dly = struct.unpack_from('<hhHH', b, o); o += 8
    out.update(temp_loop_dly_ms=t, pow_est_smooth_flag=p, pt_lvl_switch_en=lvl, pt_masking_delay_ms=dly)
    more, o = fields(['pt_masking_thr_q27', 'hist_buf_length', 'rx_static_gain_q27', 'dyn_proc_delay_ms',
                      'log_dump_en_flag', 'logging_count_period', 'fpilot'], b, o)
    out.update(more)
    out['_note'] = 'legacy layout: V7 cps_sampling_rate/chip/cps_mode_flag absent'
    assert o == len(b)
    return out


DYN_HDR = ('link_all_channels_gain temp_control_mthd temp_nominal_q6 temp_min_q6 temp_max_q6 '
           'temp_max_chg_sec_q6 temp_smoothing_factor_q31 max_attenuation_db_q7 '
           'attack_gain_smoothing_factor release_gain_smoothing_factor temp_dead_zone_q6 '
           'dead_zone_scaling_q15 clip_time_out_ms vbat_time_out_ms link_all_channels_ex_gain '
           'max_release_time_ms dyn_proc_type dyn_proc_fc_q20 dyn_proc_Q_q24 dyn_proc_threshold_dBq23 '
           'dyn_proc_ratio_q24 dyn_proc_makeup_gain_q27 dyn_proc_attack_time_ms dyn_proc_release_time_ms '
           'dyn_proc_auto_release_flag lfsn_type lfsn_fc_q20 lfsn_Q_q24 lfsn_min_gain_q27 '
           'lfsn_attack_time_ms lfsn_release_time_ms lfsn_auto_release_flag exc_ctrl_attack_time_ms '
           'exc_ctrl_release_time_ms exc_ctrl_auto_release_flag exc_ctrl_min_gain_q27 '
           'pow_lim_enable_flag limiter_attack_time_ms limiter_release_time_ms '
           'limiter_auto_release_flag num_ch').split()
TH_CTRL = ('pi_scale_u16q18 rx_scale_u16q16 r_spk_coil_q8 v_full_scale_q10 thermal_resistance_q6 '
           'thermal_time_constant_low_q10 thermal_time_constant_high_q10 temp_tgt_q6 '
           'pi_ctrl_prop_value_q12 pi_ctrl_intg_value_q12').split()
EX_CTRL = ('amp_gain_q24 ptone_excursion_mm_q27 dc_excursion_mm_q27 max_excursion_mm_q27 '
           'max_amplitude_q27 max_power_W_q27 trace_resistance_rx_q24 exc_model_tuning_factor_q27 '
           'Re_ohm_q24 Bl_q24 Mms_gram_q24 Rms_KgSec_q24 Kms_Nmm_q24 Qms_q24 Fres_Hz_q20 '
           'dc_sensitivity_Vmm_q24').split()


def dynamic_cfg(b):
    notch, o = nch_filt(b, 0)
    hdr, o = fields(DYN_HDR, b, o)
    n = hdr['num_ch']
    th = []
    for _ in range(n):
        f, o = fields(TH_CTRL, b, o)
        th.append(f)
    ex = []
    for _ in range(n):
        f, o = fields(EX_CTRL, b, o)
        f['band_splitting_even_filter_cfg'], o = tdf2(b, o)
        f['band_splitting_odd_filter_cfg'], o = tdf2(b, o)
        ex.append(f)
    assert o == len(b), (o, len(b))
    return {'rx_notch_filter_cfg': notch, **hdr, 'th_ctrl': th, 'ex_ctrl': ex,
            '_note': 'legacy layout: no filterbank_type, ex_ctrl has no FIR band splitter'}


def powlim_mode2(b):
    out, o = fields(['mode2power_limiter_attack_time_ms', 'mode2power_limiter_release_time_ms',
                     'temp_nominal_q22', 'temp_tgt_q22', 'temp_delta_q22', 'num_ch'], b)
    out['PowerW_RolloffEnd_q27'] = [q(v, 27) for v in struct.unpack_from(f'<{out["num_ch"]}I', b, o)]
    return out


def tmax_xmax_extn(b):
    n, mode = struct.unpack_from('<II', b, 0)
    rest = struct.unpack_from(f'<{(len(b) - 8) // 4}i', b, 8)
    return {'num_ch': n, 'Mode': mode, 'values_q6_C': [q(v, 6) for v in rest],
            '_note': 'Tmax[num_ch] then probably Xmax/other per-ch thresholds'}


def asp_calib(b):
    g, period, ramp = struct.unpack('<III', b)
    return {'initial_target_gain_q31': q(g, 31), 'initial_target_gain_period_in_msec': period,
            'rampup_transition_time_in_msec': ramp}


def cps2(b):
    att, rel, n = struct.unpack_from('<iii', b, 0)
    o = 12
    chs = []
    for _ in range(n):
        f, o = fields(['battery_configuration', 'Vph_WSA_min_q24', 'Ibatt_max_per_channel_q24',
                       'Iboost_throttled_perchannel_q24', 'Rph_series_q24', 'PA_eta_q24'], b, o)
        f['pbxo_even'], o = tdf2(b, o)
        f['pbxo_odd'], o = tdf2(b, o)
        g, o = fields(['clip_detect_hold_time_ms', 'clip_detect_attenuation_perframe_q27',
                       'clip_detect_max_attenuation_thr_q27',
                       'battery_config_low_frequency_attenuation_q27', 'Vph_WSA_throttlelvl_q24',
                       'Vph_WSA_max_q24', 'CPS2_max_inst_power_limit_W_q24'], b, o)
        f.update(g)
        chs.append(f)
    assert o == len(b)
    return {'clipdetect_limiter_attack_time_ms': att, 'clipdetect_limiter_release_time_ms': rel,
            'num_ch': n, 'ch': chs}


EX_VI_TS = ('Re_ohm_q24 Le_mH_q24 L2_mH_q24 R2_ohm_q24 Bl_q24 Mms_gram_q24 Rms_KgSec_q24 '
            'Kms_Nmm_q24 Fres_Hz_q20 Qms_q24').split()


def ex_vi_dynamic(b):
    n, = struct.unpack_from('<I', b, 0)
    per = (len(b) - 4) // n
    spk = []
    for i in range(n):
        f, _ = fields(EX_VI_TS, b, 4 + i * per)
        spk.append(f)
    return {'num_ch': n, 'bytes_per_ch': per, 'thiele_small': spk,
            '_note': 'legacy per-ch struct is 520 B (V7 sp_vi_ex_spkr_param_t is 532 B); '
                     'only leading T/S fields decoded'}


def raw_u32(b):
    return list(struct.unpack_from(f'<{len(b) // 4}I', b))


DECODERS = {
    # RX (MID 0x070010E2)
    0x080011E8: ('SP_STATIC_CFG', static_cfg),
    0x080011EA: ('SP_TRANSITION_ASP_ENABLE', raw_u32),
    0x080011EB: ('SP_TRANSITION_ASP_CALIB_PARAM', asp_calib),
    0x080011ED: ('SP_TH_DEMO_CFG', lambda b: dict(zip(('dsr', 'lpass_alph_q16'), struct.unpack('<HH', b)))),
    0x080011EE: ('SP_EX_DEMO_CFG', lambda b: {'dsr': struct.unpack('<H', b)[0]}),
    0x08001532: ('SP_DYNAMIC_CFG', dynamic_cfg),
    0x08001314: ('SP_TH_PI_DERV_CTRL_CFG (by layout)',
                 lambda b: {'num_ch': raw_u32(b)[0], 'pi_ctrl_derv_value_q12': [q(v, 12) for v in raw_u32(b)[1:]]}),
    0x0800135A: ('SP_EX_RX_POWLIM_MODE2_CFG', powlim_mode2),
    0x08001367: ('SP_TMAX_XMAX_LOGGING_EXTN (by layout)', tmax_xmax_extn),
    0x0800150E: ('SP_EX_RX_CPS2_PARAM', cps2),
    0x08001258: ('SP_CPS_STATIC_CFG (1520 B, gain tables)',
                 lambda b: dict(zip(('limiter_cps_en_flag', 'limiter_cps_smooth_VbDT_en_flag'),
                                    struct.unpack_from('<HH', b))) | {'limiter_cps_margin_dB': q(struct.unpack_from('<i', b, 4)[0], 15)}),
    0x0800134A: ('SP_RX_CPS_FINE_PARAM (2188 B, gain tables)',
                 lambda b: {'cps_fine_tbl_en_flag': struct.unpack_from('<H', b)[0]}),
    0x0800125A: ('SP_EX_CPS_DEMO_CFG', lambda b: {'dsr': struct.unpack('<H', b)[0]}),
    0x0800150A: ('unknown (num_ch + 4 x Q27)', lambda b: {'num_ch': raw_u32(b)[0], 'vals_q27': [q(v, 27) for v in raw_u32(b)[1:]]}),
    0x0800150B: ('unknown (num_ch + 4 x u32)', raw_u32),
    0x0800150C: ('unknown 2 B demo cfg (CPS3?)', lambda b: {'dsr': struct.unpack('<H', b)[0]}),
    # VI (MID 0x070010E3)
    0x08001384: ('SP_EX_VI_DYNAMIC_CFG (legacy)', ex_vi_dynamic),
}


def main():
    for e in json.load(open(sys.argv[1])):
        dec = DECODERS.get(e['pid'])
        if not dec:
            continue
        name, fn = dec
        print(f'== iid={e["iid"]:#x} mid={e["mid"]:#x} pid={e["pid"]:#x} {name}')
        print(json.dumps(fn(bytes.fromhex(e['data'])), indent=1, default=list))


if __name__ == '__main__':
    main()
