#!/bin/sh
# Build the Vivobook S15 speaker protection topology (ALSA topology for qcom AudioReach).
#   topology/build.sh <out.bin> [tools/sp_blob.py options, e.g. --temp-tgt 35 | --xmax 0.1]
# Needs git, python3, m4 and alsatplg (alsa-utils). The speaker parameters come from
# acdb/sp_params.json (extracted from the Windows ACDB, see README).
set -eu
top=$(cd "$(dirname "$0")/.." && pwd)
out=$(realpath -m "$1"); shift
ar="$top/topology/third_party/audioreach-topology"
if [ ! -d "$ar" ]; then
	git clone -q https://github.com/linux-msm/audioreach-topology "$ar"
	git -C "$ar" checkout -q d6bb205
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$ar/." "$tmp/"
cp -r "$top/topology/sp" "$tmp/sp"
# IIDs of the SP RX / SP VI modules in this topology
python3 -I "$top/tools/sp_blob.py" "$top/acdb/sp_params.json" 0x6053 0x61a3 "$@" > "$tmp/sp/sp_cfg.m4"
(cd "$tmp" && m4 -I . "$top/topology/X1E80100-ASUS-Vivobook-S15-SP.m4" > tplg.conf)
alsatplg -c "$tmp/tplg.conf" -o "$out" 2>&1 | grep -v "undefined s" || true
ls -la "$out"
