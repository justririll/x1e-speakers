# Speaker protection parameters from the Windows ACDB

`sp_params.json` holds the speaker protection calibration of the Vivobook S15 speakers as the
Windows audio driver ships it: every parameter of the SP RX (instance `0x411a`, module
`0x070010E2`) and SP VI (`0x4121`, `0x070010E3`) modules of subgraph `0xb0000001`.

These are Qualcomm/Asus data, not ours: they come from `acdb_cal.acdb` of the Windows driver
package `qcacsp_crd8380` 1.0.4516.4001 (02/2026), found in the Windows DriverStore. The SP values
are identical in the 1.0.4160.* packages, only the instance IDs differ. They are here so the
topology can be built without a Windows install; if the owners object they will be removed.

## Extract them yourself

From a Windows install (or the Asus/Qualcomm audio driver package):

```sh
# e.g. /mnt/win/Windows/System32/DriverStore/FileRepository/qcacsp_crd8380.inf_*/acdb_cal.acdb
python3 tools/acdb_dump.py path/to/acdb_cal.acdb --json acdb/sp_params.json
python3 tools/sp_decode.py acdb/sp_params.json      # human-readable VI params
python3 tools/sp_rx_decode.py acdb/sp_params.json   # human-readable RX params
```

`topology/build.sh` turns them into module config blobs (`tools/sp_blob.py`), with a few changes
for the Linux graph: RX input is 16 bit, VI runs at 48 kHz instead of 8 kHz, and an R0/T0
parameter with the ACDB "safe" values is added (Windows sets per-unit values at runtime).

## Key values (decoded)

| | left | right |
|---|---|---|
| R0 safe at T0 25 °C | 7.345 Ω | 7.567 Ω |
| Re (model) | 7.39 Ω | 7.66 Ω |
| Bl | 1.60 | 1.58 |
| Fres | 522 Hz | 516 Hz |
| V full scale | 13.64 V | 13.94 V |

Thermal target 80 °C (max rated 100 °C), Rth 37.3 °C/W, time constants 1.85 s / 7.41 s,
Xmax 0.4 mm, Pmax 8 W, max attenuation −12 dB; VI: 2 speakers, pilot tone 40 Hz.
