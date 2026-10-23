# Speaker protection for the Asus Vivobook S15 (S5507QA, X1E-78-100, 2x WSA8845).
#
# Import this module, set hardware.x1e-speakers.enable = true and add the kernel patches
# (kernel/*.patch, not kernel/debug/) to your kernel, e.g. with x1e-speakers = this repo:
#   boot.kernelPatches = map (n: { name = n; patch = "${x1e-speakers}/kernel/${n}"; })
#     (lib.sort lib.lessThan (lib.filter (lib.hasSuffix ".patch")
#       (lib.attrNames (builtins.readDir "${x1e-speakers}/kernel"))));
#
# - DT overlay: "WSA VI Capture" BE link for the amplifiers' V/I feedback.
# - Topology with speaker protection RX (playback) and VI (feedback) modules and the
#   Windows ACDB tuning (topology/prebuilt, or build your own with topology/build.sh).
# - spkr-vi-feedback service: keeps the V/I feedback running, mutes on failures.
# - spkr-temp: rough live coil temperature estimate.
{ config, lib, pkgs, ... }:

let
  cfg = config.hardware.x1e-speakers;
  root = ../.;

  tplg = pkgs.runCommand "vivobook-s15-spkr-prot-tplg" { } ''
    dir=$out/lib/firmware/qcom/x1e80100
    mkdir -p $dir
    cp ${cfg.topology} $dir/X1E80100-ASUS-Vivobook-S15-tplg.bin
  '';
in
{
  options.hardware.x1e-speakers = {
    enable = lib.mkEnableOption "WSA884x speaker protection (V/I feedback + DSP protection) on the Vivobook S15";

    topology = lib.mkOption {
      type = lib.types.path;
      default = root + "/topology/prebuilt/X1E80100-ASUS-Vivobook-S15-tplg.bin";
      description = "ALSA topology with the speaker protection modules.";
    };

    windowsGain = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Vendor (Windows) gain staging: DRE controlled PA gain up to +21 dB and no kernel
        speaker volume limits. Much louder. Only with working speaker protection: check
        `journalctl -u spkr-vi-feedback` and `spkr-temp` first.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    hardware.firmware = [ (lib.hiPrio tplg) ];

    hardware.deviceTree.overlays = [{
      name = "x1e80100-asus-vivobook-s15-wsa-vi";
      filter = "x1e80100-asus-vivobook-s15";
      dtsFile = root + "/dts/x1e80100-asus-vivobook-s15-wsa-vi.dtso";
    }];

    systemd.services.spkr-vi-feedback = {
      description = "WSA speaker protection V/I feedback";
      wantedBy = [ "multi-user.target" ];
      after = [ "sound.target" "sys-kernel-debug.mount" ];
      path = with pkgs; [ alsa-utils coreutils gnugrep gnused util-linux pulseaudio ];
      serviceConfig = {
        ExecStart = "${pkgs.bash}/bin/sh ${root + "/userspace/spkr-vi-feedback.sh"}";
        Restart = "always";
        RestartSec = 2;
      };
    };

    environment.systemPackages = [
      (pkgs.writeScriptBin "spkr-temp"
        ("#!${pkgs.python3}/bin/python3\n" + builtins.readFile (root + "/userspace/spkr-temp.py")))
    ];

    boot.extraModprobeConfig = lib.mkIf cfg.windowsGain ''
      options snd_soc_wsa884x pa_dre_gain=1
      options snd_soc_x1e80100 speaker_protection=1
    '';
  };
}
