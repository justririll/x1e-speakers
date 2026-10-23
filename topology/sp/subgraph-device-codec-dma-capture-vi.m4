# Copyright, Linaro Ltd, 2023
# SPDX-License-Identifier: BSD-3-Clause
include(`audioreach/audioreach.m4') dnl
include(`util/pcm.m4') dnl
include(`audioreach/subgraph.m4') dnl
include(`audioreach/container.m4') dnl
include(`audioreach/module_log.m4') dnl
include(`audioreach/module_codec_dma.m4') dnl
include(`sp/module_sp.m4') dnl
include(`sp/sp_cfg.m4') dnl
include(`util/mixer.m4') dnl
dnl
#
# SubGraph for Device Backend
#
#             ___________________________
#             |   Sub Graph              |
# [KControl]->| [DEVICE-TX] <- [LOGGER]  |
#  Switch     |__________________________|
undefine(`CDC_DMA_MODULE_IID') dnl
undefine(`LOG_MODULE_IID') dnl
undefine(`SPLIT_MODULE_IID') dnl
undefine(`SPVI_MODULE_IID') dnl
undefine(`SG_INDEX') dnl
undefine(`CONTAINER_INDEX') dnl
undefine(`MOD_INDEX') dnl

undefine(`DEVICE_PERF_MODE') dnl
undefine(`DEVICE_DIRECTION') dnl
undefine(`CONT_SENARIO_ID') dnl
undefine(`CONT_CAP') dnl
undefine(`CONT_POSITION') dnl
undefine(`DEVICE_DOMAIN_ID') dnl
undefine(`CONT_STACK_SIZE') dnl
define(`DEVICE_PERF_MODE', APM_SG_PERF_MODE_LOW_LATENCY) dnl'
define(`DEVICE_DIRECTION', APM_SUB_GRAPH_DIRECTION_TX) dnl'
define(`CONT_SENARIO_ID', APM_SUB_GRAPH_SID_AUDIO_RECORD) dnl'
define(`CONT_CAP', `ifelse(LPASS_VER_COMPAT, 110000, APM_CONTAINER_TYPE_ID_GC, APM_CONTAINER_CAP_ID_EP)') dnl'
define(`CONT_POSITION', APM_CONT_GRAPH_POS_GLOBAL_DEV)dnl'
define(`DEVICE_DOMAIN_ID', ifdef(`AR_SELECTED_PROC_DOMAIN_ID', `AR_SELECTED_PROC_DOMAIN_ID', `APM_PROC_DOMAIN_ID_ADSP')) dnl'
define(`CONT_STACK_SIZE', 8192) dnl'

define(`CDC_DMA_MODULE_IID', MOD_IID_START) dnl
define(`LOG_MODULE_IID', eval(MOD_IID_START + 1)) dnl
define(`SPLIT_MODULE_IID', eval(MOD_IID_START + 2)) dnl
define(`SPVI_MODULE_IID', eval(MOD_IID_START + 3)) dnl
dnl SP RX lives in the WSA_CODEC_DMA_RX_0 device graph (mod-iid-start 0x6050 + 3), open before VI
define(`SP_RX_IID', `0x6053') dnl
define(`SG_INDEX', 1) dnl
define(`CONTAINER_INDEX', 1) dnl
define(`MOD_INDEX', 1) dnl
dnl
dnl DEVICE_CAPTURE_ROUTE(stream-index, dai-id)
define(`DEVICE_CAPTURE_ROUTE',
`'
`SectionGraph."NAME_PREFIX.$1 $2 Graph" {'
`        index STR($1)'
`        lines ['
`                "NAME_PREFIX.codec_dma_tx$1, , $2 Capture"'
`                "NAME_PREFIX.splitter$1, , NAME_PREFIX.codec_dma_tx$1"'
`                "NAME_PREFIX.logger$1, , NAME_PREFIX.splitter$1"'
`                "NAME_PREFIX.sp_vi$1, , NAME_PREFIX.splitter$1"'
`        ]'
`}')

AR_SUBGRAPH(SG_INDEX, DEVICE_DAI_ID, SG_IID_START, DEVICE_PERF_MODE, DEVICE_DIRECTION, CONT_SENARIO_ID)

AR_CONTAINER(CONTAINER_INDEX, CONT_IID_START, CONT_CAP, CONT_STACK_SIZE, CONT_POSITION, DEVICE_DOMAIN_ID)

AR_MODULE_CODEC_DMA_TX(MOD_INDEX, SG_INDEX, CONTAINER_INDEX, CDC_DMA_MODULE_IID, 0, 1, 1, 2, DEVICE_INTF_TYPE, DEVICE_INTF_INDEX, DEVICE_DATA_FORMAT, `DEVICE_NAME', SPLIT_MODULE_IID)
AR_MODULE_SPLITTER2(MOD_INDEX, SG_INDEX, CONTAINER_INDEX, SPLIT_MODULE_IID, LOG_MODULE_IID, SPVI_MODULE_IID)
AR_MODULE_SP(sp_vi, MOD_INDEX, SG_INDEX, CONTAINER_INDEX, SPVI_MODULE_IID, MODULE_ID_SPEAKER_PROTECTION_VI, 1, 0, `SP_VI_CFG_BYTES', 0, 0, NONE_IID,
	SP_CTRL_PORT, SP_RX_IID, SP_CTRL_PORT, INTENT_ID_SP)
AR_MODULE_LOG(   MOD_INDEX, SG_INDEX,       CONTAINER_INDEX, LOG_MODULE_IID,     1, 1, 1, 2, 0x000019ab, 1, 0, NONE_IID)
dnl kcontrol switch
DEVICE_CAPTURE_MIXER(SG_INDEX, `DEVICE_NAME')
DEVICE_CAPTURE_ROUTE(MOD_INDEX, `DEVICE_NAME')
