# x1e-speakers

DSP speaker protection for the **Asus Vivobook S15 (S5507QA, Snapdragon X Elite X1E-78-100)**
on Linux: the WSA8845 amplifiers' voltage/current feedback, the Qualcomm Speaker Protection
(SPv5) modules in the ADSP with the Windows tuning, and the Windows gain staging.

> [!WARNING]
> **Experimental and vibe-coded.** Most of this was written together with an AI assistant
> (Claude), reverse engineered from the Windows driver and tested on **one laptop only: the Asus
> Vivobook S15 S5507QA with the X1E-78-100**. The tests so far suggest that it works: the
> thermal and excursion protection react as expected, see [Status](#status). But it is **not 100%
> verified**, and **there is no warranty of any kind**. Laptop speakers can be damaged instantly
> and permanently by too much excursion. Use at your own risk, and read the whole README first.

## Why

Mainline Linux has no speaker protection on X1E laptops, so it limits the WSA volumes
(−3 dB digital, 0 dB PA gain). The speakers are quiet, and even with the limits people have
reported damaged speakers. On Windows the ADSP runs speaker protection with live V/I feedback:
it keeps the coil below its thermal target (80 °C here) and the cone excursion below Xmax
(0.4 mm), and the amplifiers run at full gain.

This repo does the same on Linux:

- **kernel/**: patches for the WSA884x V/I sense capture, S32 V/I capture, AudioReach module
  config blobs and control links from the topology, the SP VI channel map, and two module
  parameters for the Windows gain staging (both off by default).
- **dts/**: DT overlay adding the "WSA VI Capture" link and fixing the SoundWire block packing
  of the VI ports.
- **topology/**: ALSA (AudioReach) topology with SP RX on speaker playback and SP VI on the V/I
  feedback, linked, carrying the Windows ACDB parameters. Prebuilt and source.
- **userspace/**: `spkr-vi-feedback.sh` keeps the V/I feedback running while the speakers play,
  and mutes the speakers if the feedback goes missing. `spkr-temp.py` shows a rough live coil
  temperature estimate.
- **acdb/**: the speaker parameters extracted from the Windows ACDB, and how to extract them.
- **tools/**: ACDB parser and decoders, the blob generator, and analysis scripts for V/I captures.
- **docs/NOTES.md**: how it all works, findings, test results.
- **nixos/**: an optional NixOS module that sets all of the above up.

## Status

Tested on the S5507QA (details in [docs/NOTES.md](docs/NOTES.md#tests-on-the-s5507qa-quiet-unless-noted)):

- V/I feedback: correct V and I data for both speakers. Factory test mode measures R = 7.44 / 8.20 Ω.
- Thermal protection: with a test target of 35 °C, the coil temperature stopped at the target
  and the level went down smoothly by 1.1 dB.
- Excursion protection: with a test Xmax of 0.1 mm, bass was cut by 6–12 dB.
- With the Windows gain: the output matches the SP model, quiet tones are not attenuated, and
  about an hour of music at full volume (including bass boosted tracks) worked without problems.
- The feedback survives PipeWire stream restarts and suspend/resume.

Not verified / known issues:

- Excursion protection at high levels was only checked indirectly: no measurement of the actual
  cone movement. If you hear rattling, buzzing or clicks, turn it down.
- R0 is not calibrated per unit: the ACDB "safe" values are used, like Windows does without
  calibration. Here that makes the protection see the coils somewhat hotter than they are.
- Sometimes a playback start leaves the amplifiers without V/I data for the whole stream. Cause
  unknown, see [Known issues](docs/NOTES.md#known-issues). The service detects it within about
  a second, mutes, and restarts the playback, so there is a short gap. It also logs the
  amplifier registers.
- Only the Vivobook S15 S5507QA. Other X1E laptops with WSA884x need their own DT overlay,
  topology and ACDB values. Do not use this tuning on other speakers.

## Requirements

- Linux 7.3 (the patches are against 7.3-rc7 with the usual X1E laptop support; other trees may
  need small rebasing).
- The ADSP firmware from Windows (the Linux one is the same image) and the T14s/Vivobook UCM
  profile from alsa-ucm-conf (speakers on `hw:N,1`).
- For the service: alsa-utils, coreutils, grep, sed, util-linux (`runuser`) and `pactl`
  (pipewire-pulse or pulseaudio). To build the topology: git, python3, m4, alsatplg.

## Installation

### 1. Kernel

```sh
cd linux
git am /path/to/x1e-speakers/kernel/*.patch
```

Build and install as usual. `kernel/debug/` has two optional debugging patches: a VI channel mask
parameter and a debugfs interface for raw module parameter get/set. They are not needed.

### 2. Device tree overlay

```sh
dtc -@ -I dts -O dtb -o wsa-vi.dtbo dts/x1e80100-asus-vivobook-s15-wsa-vi.dtso
fdtoverlay -i x1e80100-asus-vivobook-s15.dtb -o x1e80100-asus-vivobook-s15.dtb.new wsa-vi.dtbo
```

Boot with the new DTB, or load the `.dtbo` through your boot loader.

### 3. Topology

```sh
install -m644 topology/prebuilt/X1E80100-ASUS-Vivobook-S15-tplg.bin \
    /lib/firmware/qcom/x1e80100/X1E80100-ASUS-Vivobook-S15-tplg.bin
```

This replaces the linux-firmware topology. An uncompressed file is loaded before a `.zst`/`.xz`
one, but check that nothing reinstalls the distribution's file over yours.

To build it yourself, run `topology/build.sh out.bin`. Options like `--temp-tgt 35` or
`--xmax 0.1` make test builds with a lower thermal target or Xmax, to check that the protection
reacts without loud tests.

### 4. V/I feedback service

```sh
install -m755 userspace/spkr-vi-feedback.sh /usr/local/lib/spkr-vi-feedback.sh
install -m644 userspace/spkr-vi-feedback.service /etc/systemd/system/
systemctl enable --now spkr-vi-feedback
install -m755 userspace/spkr-temp.py /usr/local/bin/spkr-temp
```

Reboot, play something quiet and check:

```sh
journalctl -u spkr-vi-feedback -f   # "V/I feedback started", no WARNING/ERROR
spkr-temp                           # R/R0, rough coil temperature, V rms, state
```

`spkr-temp` uses a cold reference measured on one unit (`REF` in the script). It is only a rough
estimate; the DSP's own measurement is what limits the speakers.

### 5. Windows gain staging (optional, much louder)

Only after step 4 works. **Lower the volume first**: the same volume setting is about 20 dB louder.

```
# /etc/modprobe.d/x1e-speakers.conf
options snd_soc_wsa884x pa_dre_gain=1
options snd_soc_x1e80100 speaker_protection=1
```

`pa_dre_gain` lets the amplifier DRE control the PA gain up to +21 dB like Windows does.
`speaker_protection` removes the kernel's WSA volume limits. Without them you still get the
protection, just at the old (quiet) volume.

### NixOS

`nixos/x1e-speakers.nix` is a module for steps 2–5:
`hardware.x1e-speakers.enable = true;` and `hardware.x1e-speakers.windowsGain = true;`.
The kernel patches still need to be added to your kernel; the module's header has an example.

## How the fail-safe works

The service checks a 50 ms V/I probe every second. If there is no data (all words
`0x80008000`) or the capture stalls:

1. It restarts the capture once.
2. It mutes the speakers (WSA digital volume 0; neither UCM nor PipeWire touches it) and restarts
   the playback by suspending the PipeWire speaker sink for half a second.
3. When V/I data comes back, it restores the volume. The saved volume is kept in
   `/var/lib/spkr-vi-feedback/` and survives a reboot.

## Data and license

The code and patches are GPL-2.0-only (see `LICENSE`). The topology m4 files build on
[audioreach-topology](https://github.com/linux-msm/audioreach-topology) (BSD-3-Clause).

`acdb/sp_params.json` and the prebuilt topology contain speaker calibration data from the
Qualcomm/Asus Windows driver (`acdb_cal.acdb`). They are not covered by the license above and
belong to their owners. They are included so the topology can be built without Windows, and
[acdb/README.md](acdb/README.md) explains how to extract them from your own copy.
