# Technical notes

Findings from getting Qualcomm speaker protection (SPv5) running on the Vivobook S15 (S5507QA,
X1E-78-100) under Linux. Everything here was found on that one laptop.

## Hardware and signal path

```
PipeWire -> hw:N,1 (MultiMedia2) -> ADSP: [stream graph] -> [WSA RX device graph:
            LOG -> MFC -> SP RX (0x6053) -> CODEC_DMA_SINK] -> wsa_macro -> SoundWire 6b10000
            -> 2x WSA8845 (DAC, COMP, BOOST, PBR, CPS ports) -> speakers
                                     |
amplifier VISENSE (port 5) -> SoundWire master ports 10/11 -> wsa_macro AIF_VI
            -> WSA_CODEC_DMA_TX_0 -> ADSP: [VI graph: CODEC_DMA_SOURCE -> SPLITTER
            -> SP VI (0x61a3) + LOG] -> MultiMedia5 (hw:N,4)
SP VI --control link (intent 0x08001204)--> SP RX
```

- The SP RX module sits in the playback chain and sets the gain. SP VI gets the measured
  voltage/current of each coil, estimates R (temperature) and sends it to SP RX over the
  control link. Without the VI graph running, SP RX only has its model.
- The VI graph only runs while something captures MultiMedia5: `userspace/spkr-vi-feedback.sh`
  does that while the speakers are powered (wsa884x DAPM "SPKR" widget on) and restarts the
  capture when the playback stream restarts (the control link binds to the RX module of the
  playback graph that is open when VI starts). Starting VI before playback hangs the APM.
- The UCM profile (shared with the T14s) uses MultiMedia4 for the internal microphones, so VI
  got its own front end, MultiMedia5.

## V/I data format

- SoundWire: VISENSE is slave port 5 of each WSA884x, mapped to master ports 10 (left) and 11
  (right), 2 channels (V, I), 1 bit per sample interval (PDM-like, `bps = 1`).
- wsa884x VISENSE is a simple data port without BlockCtrl3, so it always uses per-port block
  packing. The X1E DT sets per-channel packing for ports 10/11 on the master; with both channels
  enabled that gives garbage. The DT overlay sets `qcom,ports-block-pack-mode` to 0 for them.
- DMA: S32_LE, 2 channels (left, right amplifier). Each 32-bit word is V in bits 31..16 and I in
  bits 15..0 (signed 16 bit). 32768 = 13.64 V full scale. S16 and S24 cut I off (S24 arrives
  packed in 3 bytes from the DSP), hence the q6apm-dai S32_LE capture patch.
- No data looks like `0x80008000` (or 0) in every word. On digital silence the data is alive:
  noise plus the 40 Hz pilot tone of SP RX.
- The SP VI channel map must be `[2, 1, 4, 3]` (I first, then V, per speaker), not the
  `[1, 2, 3, 4]` the kernel sent.

## Module configuration

- The topology carries the Windows ACDB parameters as AudioReach `MODULE_CFG` blobs
  (`0x01001006`): a 16-byte header `{size incl. header, type, priv[2]}` followed by
  `APM_CMD_SET_CFG` style params. The kernel patches send them module by module (and fix the
  blob size handling, which was off by the header).
- **R0/T0**: the kernel selects "calibrated" R0/T0 (`th_r0t0_selection = 0`) but nothing sent
  `PARAM_ID_SP_TH_VI_R0T0_CFG` (0x080011F5), so the module used R0 = 2.0 Ω, saw a "hot" coil and
  held −12 dB. The blob now sets R0 to the ACDB safe values (7.345 / 7.567 Ω at 25 °C). The
  measured cold R (factory test mode) is 7.44 / 8.20 Ω, so with the safe values the module sees
  the coils somewhat hotter than they are (limits earlier, not later).
- VI runs at 48 kHz. 8 kHz (the ACDB value) next to 48 kHz playback gave SoundWire bus clashes
  and parity errors.
- RX dynamic config `0x08001532`: `temp_tgt_q6` at offsets 312/352 (80 °C), `max_excursion_mm_q27`
  at 376/688 (0.4 mm). `tools/sp_blob.py --temp-tgt C` / `--xmax MM` change them for tests.

## Control link

`APM_PARAM_ID_MODULE_CTRL_LINK_CFG` in GRAPH_OPEN, per link 48 bytes: peer 1 IID/port, peer 2
IID/port, 2 properties `{0x08001062, 8, 1, intent}`, `{0x0800136f, 4, 1}`. Windows links
`0x4121:0x80000000 <-> 0x411a:0x80000000`, intent `0x08001204`. Topology tokens 277..280
(see `topology/sp/tokens.m4`).

## Gain staging

- Mainline limits the WSA digital volume to −3 dB and the PA volume to 0 dB on x1e80100
  because there was no protection. The PA volume is the CSR gain in `DRE_CTL_1`: the limit gives
  a manual CSR code 25; code 0 is G_21_DB, steps of 1.5 dB.
- Windows writes `DRE_CTL_1 = 0` (CSR off, DRE controlled gain up to +21 dB). The SP model
  assumes that gain (0 dBFS = 13.64 V on the speaker). With the Linux limits the protection is
  very conservative because the real output is ~20 dB below what it models.
- `snd_soc_wsa884x.pa_dre_gain=1` and `snd_soc_x1e80100.speaker_protection=1` give the Windows
  gain staging. Checked: the measured output matches the SP model within 0.6 dB.

## Tests (on the S5507QA, quiet unless noted)

| test | result |
|---|---|
| factory test mode (FTM) | R = 7.44 / 8.20 Ω |
| tones −30 dBFS, Windows gain | no attenuation except the constant −2.9 dB (pilot headroom) |
| pink noise −26/−20/−14 dBFS, 30 s | coil +1 / +1 / +4 °C |
| thermal target set to 35 °C, −14 dBFS 140 s | rise stopped at the target, smooth −1.1 dB (channels linked) |
| Xmax set to 0.1 mm instead of 0.4, bass tones −20 dBFS | 60 Hz −6 dB, 100/200 Hz −12 dB vs. baseline |
| 20+ quiet PipeWire stream restarts, suspend/resume | V/I feedback restarts every time |
| music at full volume, Windows gain, ~1 h | coils held around 60–75 °C (rough estimate), no failures except below |

## Known issues

- **V/I lost for a whole stream** (about 4 times in an hour of loud music, 0 of 50+ quiet starts):
  some playback starts (mostly loud track starts) leave the amplifiers without V/I data until the
  speakers power down; restarting the capture does not help. In 2 of 4 cases the right amplifier
  logged SoundWire parity errors / "Test fail for port 2" / bus clash before VI started, in the
  others nothing. Not a hwmon temperature read race (tested). Cause unknown; the service logs the
  amplifiers' PA FSM / IV sense / interrupt registers on the first failure (`amp N: ...` in the
  journal; healthy: `0x3435` = 0x2f, `0x3026` = 0x10, `0x3034` = 0x80, errors 0) and recovers by
  muting and restarting the playback.
- The first speaker stream after boot sometimes had no V/I data before the service waited for the
  playback PCM to be RUNNING (not only prepared) and warmed up the path at boot.
- Never read LPASS MMIO registers (e.g. via /dev/mem) while no audio stream runs: unclocked
  access hangs the SoC.
