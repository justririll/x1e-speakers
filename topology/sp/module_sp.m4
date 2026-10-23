# SPDX-License-Identifier: BSD-3-Clause
# Speaker protection (SPv5, legacy module IDs as used by the X1E ADSP) and splitter modules.
include(`util/util.m4') dnl
define(`MODULE_ID_SPEAKER_PROTECTION', `0x070010E2') dnl
define(`MODULE_ID_SPEAKER_PROTECTION_VI', `0x070010E3') dnl
define(`MODULE_ID_SPLITTER', `0x07001011') dnl
define(`INTENT_ID_SP', `0x08001204') dnl
define(`SP_CTRL_PORT', `0x80000000') dnl
dnl
dnl AR_MODULE_SP(name, index, sgidx, container-idx, iid, mid, maxip, maxop,
dnl              `cfg-bytes-macro', src-port, dst-port, dst-iid,
dnl              ctrl-port, ctrl-peer-iid, ctrl-peer-port, ctrl-intent)   (ctrl-peer-iid 0 = no link)
dnl The cfg macro is passed quoted and expands to the module config blob (sp_cfg.m4).
define(`AR_MODULE_SP',
`'
`SectionVendorTuples."NAME_PREFIX.$1$2_tuples" {'
`        tokens "audioreach_tokens"'
`'
`        tuples."word.u32_data" {'
`                AR_TKN_U32_MODULE_INSTANCE_ID STR($5)'
`                AR_TKN_U32_MODULE_ID STR($6)'
`                AR_TKN_U32_MODULE_MAX_IP_PORTS STR($7)'
`                AR_TKN_U32_MODULE_MAX_OP_PORTS STR($8)'
`                AR_TKN_U32_MODULE_SRC_INSTANCE_ID STR($5)'
`                AR_TKN_U32_MODULE_SRC_OP_PORT_ID STR($10)'
`                AR_TKN_U32_MODULE_DST_IN_PORT_ID STR($11)'
`                AR_TKN_U32_MODULE_DST_INSTANCE_ID STR($12)'
`                AR_TKN_U32_MODULE_CTRL_PORT_ID STR($13)'
`                AR_TKN_U32_MODULE_CTRL_PEER_IID STR($14)'
`                AR_TKN_U32_MODULE_CTRL_PEER_PORT_ID STR($15)'
`                AR_TKN_U32_MODULE_CTRL_INTENT_ID STR($16)'
`        }'
`}'
`'
`SectionData."NAME_PREFIX.$1$2_data" {'
`        tuples "NAME_PREFIX.$1$2_tuples"'
`}'
`'
`SectionData."NAME_PREFIX.$1$2_cfg" {'
`        bytes "'$9`"'
`}'
`'
`SectionWidget."NAME_PREFIX.$1$2" {'
`        index STR($2)'
`        type "src"'
`        no_pm "true"'
`        subseq "10"'
`        data ['
`                "NAME_PREFIX.sub_graph$3_data"'
`                "NAME_PREFIX.container$4_data"'
`                "NAME_PREFIX.$1$2_data"'
`                "NAME_PREFIX.$1$2_cfg"'
`        ]'
`}') dnl
dnl
dnl AR_MODULE_SPLITTER2(index, sgidx, container-idx, iid, dst-iid0, dst-iid1): 1 in, 2 out (ports 1, 3)
define(`AR_MODULE_SPLITTER2',
`'
`SectionVendorTuples."NAME_PREFIX.splitter$1_tuples" {'
`        tokens "audioreach_tokens"'
`'
`        tuples."word.u32_data" {'
`                AR_TKN_U32_MODULE_INSTANCE_ID STR($4)'
`                AR_TKN_U32_MODULE_ID STR(MODULE_ID_SPLITTER)'
`                AR_TKN_U32_MODULE_MAX_IP_PORTS "1"'
`                AR_TKN_U32_MODULE_MAX_OP_PORTS "2"'
`                AR_TKN_U32_MODULE_SRC_INSTANCE_ID STR($4)'
`                AR_TKN_U32_MODULE_SRC_OP_PORT_ID "1"'
`                AR_TKN_U32_MODULE_DST_IN_PORT_ID "2"'
`                AR_TKN_U32_MODULE_DST_INSTANCE_ID STR($5)'
`                AR_TKN_U32_MODULE_SRC_OP_PORT_ID1 "3"'
`                AR_TKN_U32_MODULE_DST_IN_PORT_ID1 "2"'
`                AR_TKN_U32_MODULE_DST_INSTANCE_ID1 STR($6)'
`        }'
`}'
`'
`SectionData."NAME_PREFIX.splitter$1_data" {'
`        tuples "NAME_PREFIX.splitter$1_tuples"'
`}'
`'
`SectionWidget."NAME_PREFIX.splitter$1" {'
`        index STR($1)'
`        type "src"'
`        no_pm "true"'
`        subseq "10"'
`        data ['
`                "NAME_PREFIX.sub_graph$2_data"'
`                "NAME_PREFIX.container$3_data"'
`                "NAME_PREFIX.splitter$1_data"'
`        ]'
`}') dnl
