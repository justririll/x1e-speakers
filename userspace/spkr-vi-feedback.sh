#!/bin/sh
# Keep the WSA speaker V/I feedback capture running while the speakers play.
#
# Speaker protection RX (WSA playback graph) only gets the measured coil state while the
# protection VI graph runs, i.e. while something captures MultiMedia5 (WSA_CODEC_DMA_TX_0).
# The VI graph links to the RX module of the playback graph that is open when it starts,
# so it is (re)started after the speakers power up and after every playback stream restart,
# and stopped when the speakers power down. Starting VI before playback hangs the APM.
# The V/I data is checked every second; without it the capture is restarted and, if that does
# not help, the speakers are muted until feedback works again (see mute) and the playback is
# restarted (see restart_playback).
set -u

CARD_ID=${CARD_ID:-X1E80100ASUSViv}
PCM_DEV=${PCM_DEV:-4}
SPK_PCM=${SPK_PCM:-1}	# speaker playback PCM (UCM: hw:N,1)
POLL=${POLL:-0.2}

card=""
for c in /proc/asound/card[0-9]*; do
	[ "$(cat "$c/id" 2>/dev/null)" = "$CARD_ID" ] && card=${c##*card}
done
[ -n "$card" ] || { echo "card $CARD_ID not found"; exit 1; }

dapm=$(ls -d /sys/kernel/debug/asoc/*/sdw:*:0217:0204:00:0/dapm 2>/dev/null | head -n 1)
[ -n "$dapm" ] || { echo "wsa884x DAPM debugfs not found"; exit 1; }
spkr="$dapm/SpkrLeft SPKR"

ctl() { amixer -q -D "hw:$card" cset name="$1" "$2" || echo "failed to set $1"; }

setup_mixers() {
	ctl "WSA WSA_AIF_VI Mixer WSA_SPKR_VI_1" 1
	ctl "WSA WSA_AIF_VI Mixer WSA_SPKR_VI_2" 1
	ctl "MultiMedia5 Mixer WSA_CODEC_DMA_TX_0" 1
}

spkr_on() { case "$(head -n 1 "$spkr" 2>/dev/null)" in *": On"*) return 0 ;; esac; return 1; }

# Changes whenever a playback stream is (re)started
playback_key() {
	for s in /proc/asound/card"$card"/pcm*p/sub0/status; do
		grep -E "^(state|trigger_time|owner_pid)" "$s" 2>/dev/null
	done | tr -d '\n'
}

pid=""
rpid=""
key=""
probe=/run/spkr-vi-probe.raw
fifo=/run/spkr-vi.fifo
state=/var/lib/spkr-vi-feedback
retries=0
tick=0

# V/I data in the latest probe? Samples are 0x80008000 (or 0) when the amplifiers send nothing;
# with real feedback they never are, even on digital silence (pilot tone, noise).
vi_ok() {
	[ -s "$probe" ] || return 1
	[ $(( $(date +%s) - $(stat -c %Y "$probe") )) -le 3 ] || return 1	# capture stalled
	[ -n "$({ od -An -v -tx4 "$probe" | tr ' ' '\n'; } 2>/dev/null | grep -m 1 -vE '^(80008000|00000000|)$')" ]
}

# Fail-safe: without feedback the protection cannot see the coil temperature and excursion, so
# mute the speakers (WSA digital volume, not used by UCM / PipeWire) until V/I data comes back.
VOLS="WSA WSA_RX0 Digital Volume|WSA WSA_RX1 Digital Volume"
mute() {
	[ -e "$state/volume" ] && return
	mkdir -p "$state"
	amixer -D "hw:$card" cget name="WSA WSA_RX0 Digital Volume" | sed -n 's/.*: values=\([0-9]*\).*/\1/p' > "$state/volume.new"
	[ -s "$state/volume.new" ] || echo 84 > "$state/volume.new"	# 0 dB
	mv "$state/volume.new" "$state/volume"
	echo "$VOLS" | tr '|' '\n' | while read -r v; do ctl "$v" 0; done
	echo "ERROR: no V/I feedback, speakers muted until it works again"
}

unmute() {
	[ -e "$state/volume" ] || return
	vol=$(cat "$state/volume")
	echo "$VOLS" | tr '|' '\n' | while read -r v; do ctl "$v" "$vol"; done
	rm -f "$state/volume"
	echo "V/I feedback works, speakers unmuted (digital volume $vol)"
}

# Speaker playback PCM running (not only prepared: DAPM powers the speakers up at prepare)
spkr_running() { grep -q "^state: RUNNING" "/proc/asound/card$card/pcm${SPK_PCM}p/sub0/status" 2>/dev/null; }

start_vi() {
	# VI started before the playback graph runs gets no data for the whole stream, also after
	# restarts (PipeWire prepares the PCM a while before it starts it).
	for i in 1 2 3 4 5 6 7 8 9 10; do spkr_running && break; sleep 0.2; done
	spkr_running || return
	sleep 0.3	# let the playback graph start first
	spkr_on || return
	setup_mixers
	rm -f "$probe" "$fifo"
	mkfifo "$fifo"
	# A 50 ms probe of the V/I data every second for vi_ok. arecord writes to a FIFO (not a
	# pipe) so that stop_vi can kill arecord itself: when the speakers power down it blocks in
	# read and a shell pipeline job would never finish.
	{ while head -c 19200 > "$probe.new" && [ -s "$probe.new" ]; do
		mv -f "$probe.new" "$probe"
		head -c 364800 > /dev/null
	done; } < "$fifo" &
	rpid=$!
	arecord -q -D "hw:$card,$PCM_DEV" -c 2 -r 48000 -f S32_LE -t raw > "$fifo" &
	pid=$!
	key=$(playback_key)
	tick=0
	echo "V/I feedback started (pid $pid)"
}

# Diagnostics: read-only dump of the amplifiers' PA FSM state / error conditions (0x3430..0x3439),
# FSM bypass (0x343d), IV sense enable / status (0x3026, 0x3034) and interrupt status (0x3583..4)
amp_regs() {
	for d in /sys/kernel/debug/soundwire/master-*/sdw:*:0217:0204:00:*; do
		[ -e "$d/read_buffer" ] || continue
		out=""
		for r in 0x3430:10 0x343d:1 0x3026:1 0x3034:1 0x3583:2; do
			echo 0 > "$d/command_type"; echo $((${r%:*})) > "$d/start_address"
			echo 1 > "$d/command"; echo "${r#*:}" > "$d/num_bytes"; echo 1 > "$d/go"
			out="$out ${r%:*}:$(sed -n 's/.*val \(0x[0-9a-f]*\).*/\1/p' "$d/read_buffer" | tr '\n' ' ')"
		done
		echo "amp ${d##*:}: $(cat "/sys/bus/soundwire/devices/${d##*/}/status" 2>/dev/null)$out"
	done 2>/dev/null
}

# Some playback starts leave the amplifiers without V/I for the whole stream, sometimes
# because they dropped off the SoundWire bus (status UNATTACHED, register reads fail).
# Restarting the capture does not help; letting the bus runtime suspend (clock stop) and
# resume does, it enumerates the amplifiers again. PipeWire ignores sink suspends while
# streams play, so switch the card profile off for 5 s (> 3 s SoundWire autosuspend) and
# back, as the user owning the playback PCM.
restart_playback() {
	owner=$(sed -n 's/^owner_pid *: //p' "/proc/asound/card$card/pcm${SPK_PCM}p/sub0/status" 2>/dev/null)
	[ -n "$owner" ] || return
	uid=$(stat -c %u "/proc/$owner") || return
	user=$(stat -c %U "/proc/$owner") || return
	pa() { runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" pactl "$@"; }
	pcard=$(pa list cards short | sed -n 's/^[0-9]*\t\(alsa_card\.platform-sound\)\t.*/\1/p' | head -n 1)
	prof=$(pa list cards | sed -n 's/^[[:space:]]*Active Profile: //p' | head -n 1)
	[ -n "$pcard" ] && [ -n "$prof" ] || { echo "no PipeWire card to restart"; return; }
	echo "restarting speaker playback (card profile off for 5 s as $user)"
	pa set-card-profile "$pcard" off && sleep 5
	pa set-card-profile "$pcard" "$prof"
}

# No V/I data: restart the capture once, then mute and restart the playback, keep retrying
vi_failed() {
	[ "$retries" -eq 0 ] && amp_regs
	retries=$((retries + 1))
	[ "$retries" -gt 1 ] && mute
	if [ "$retries" -eq 2 ] || [ $((retries % 10)) -eq 0 ]; then
		stop_vi
		restart_playback
	elif [ "$retries" -eq 1 ] || [ $((retries % 5)) -eq 0 ]; then
		stop_vi
		start_vi
	fi
}

# Called every second while V/I runs
check_vi() {
	if vi_ok; then
		retries=0
		unmute
	else
		echo "WARNING: V/I feedback has no data"
		vi_failed
	fi
}

# The first speaker stream after boot does not get V/I data from the amplifiers (later
# ones do): run a short silent stream with V/I capture once, before anything else plays.
warm_up() {
	[ -e /run/spkr-vi-warm ] && return
	spkr_on && return
	ctl "WSA WSA RX0 MUX" AIF1_PB; ctl "WSA WSA RX1 MUX" AIF1_PB
	ctl "WSA WSA_RX0 INP0" RX0; ctl "WSA WSA_RX1 INP0" RX1
	ctl "WSA_CODEC_DMA_RX_0 Audio Mixer MultiMedia2" 1
	setup_mixers
	head -c 192000 /dev/zero > /run/spkr-vi-silence.raw
	aplay -q -D "hw:$card,1" -c 2 -r 48000 -f S16_LE -t raw /run/spkr-vi-silence.raw &
	ap=$!
	sleep 0.3
	arecord -q -D "hw:$card,$PCM_DEV" -c 2 -r 48000 -f S32_LE -d 1 -t raw /dev/null
	if wait $ap; then
		touch /run/spkr-vi-warm
		echo "warm-up done"
	else
		echo "warm-up skipped (speaker PCM busy)"
	fi
	rm -f /run/spkr-vi-silence.raw
}

stop_vi() {
	[ -n "$pid" ] || return
	kill "$pid" 2>/dev/null
	kill -CONT "$pid" 2>/dev/null	# a stopped process only ends on SIGTERM once continued
	for i in 1 2 3 4 5; do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
	kill -KILL "$pid" 2>/dev/null	# does not end on SIGTERM: do not hang here
	wait "$pid" 2>/dev/null
	wait "$rpid" 2>/dev/null
	echo "V/I feedback stopped"
	pid=""
	rpid=""
}

trap 'stop_vi; exit 0' INT TERM

setup_mixers
warm_up
while :; do
	if spkr_on; then
		if [ -z "$pid" ]; then
			start_vi
		elif [ "$(playback_key)" != "$key" ]; then
			stop_vi
			start_vi
		elif ! kill -0 "$pid" 2>/dev/null; then
			echo "WARNING: V/I capture exited"
			stop_vi
			vi_failed
		else
			tick=$((tick + 1))
			[ $((tick % 5)) -eq 0 ] && check_vi
		fi
	elif [ -n "$pid" ]; then
		stop_vi
	fi
	sleep "$POLL"
done
