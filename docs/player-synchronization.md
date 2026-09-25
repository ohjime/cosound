# Synchronized players

Run the existing player command on each computer using the **same Player token**
and backend. Those instances share one soundscape timeline while each continues
to drive its own attached audio outputs. No new administrator setting or central
audio cable is required. Different Player tokens still represent independent
players, with their own predictions; sharing a server alone does not make their
mixes identical.

This synchronizes soundscape loops and their gain transitions. It does not make
different speaker layouts produce identical channel signals, or turn separate
audio interfaces into a single addressable multichannel interface. Physical
speaker distance, device processing, and room acoustics still affect what a
listener hears.

## What BeatSync actually does

The reference studied is the supplied `beatsync-main` source tree. Paths below
are relative to its root; line numbers identify the inspected snapshot.

| Mechanism | BeatSync implementation |
| --- | --- |
| High-resolution time | `packages/shared/utils.ts:2` uses `performance.timeOrigin + performance.now()`, preserving an epoch reference while measuring elapsed time monotonically. |
| Four timestamps over WebSocket | `apps/server/src/routes/websocketHandlers.ts:164` timestamps receipt before parsing and timestamps the response immediately before sending. `apps/client/src/utils/ntp.ts:192` computes offset and round-trip delay. |
| Reject distorted timing probes | `apps/client/src/utils/ntp.ts:46` sends paired probes; `:126` compares client departure spacing with server arrival spacing. `packages/shared/constants.ts:6` sets a 25 ms gap, 5 ms tolerance, 16 retained measurements, 50 ms startup cadence, and 2.5 s steady cadence. |
| Prefer an uncongested measurement | `apps/client/src/utils/ntp.ts:166` selects the offset from the lowest-RTT measurement. `apps/client/src/store/global.tsx:1057` maintains the rolling window. |
| Prepare audio before scheduling | `apps/server/src/managers/RoomManager.ts:168` requests loading and waits for readiness, with a 3 s timeout defined at `:98`. Audio is downloaded and decoded locally; this is not an audio-streaming transport. |
| Publish a future deadline | `apps/server/src/managers/RoomManager.ts:284` broadcasts track, position, and server execution time. `:629` accounts for RTT and output compensation; `apps/server/src/config.ts:17` provides a 400 ms minimum scheduling lead. |
| Start on the audio clock | `apps/client/src/store/global.tsx:343` subtracts clock offset, output latency, and manual adjustment; `:881` captures an absolute audio deadline; `:1209` calls `AudioBufferSourceNode.start(deadline, trackOffset)`. |
| Join playback already underway | `apps/server/src/managers/RoomManager.ts:915` projects the track position forward to a future join deadline. |

The clock calculation is the standard four-timestamp construction. With client
send/receive times `t0`, `t3` and server receive/send times `t1`, `t2`:

```text
server_minus_client = ((t1 - t0) + (t2 - t3)) / 2
network_round_trip  = (t3 - t0) - (t2 - t1)
```

This removes measured server processing time. Choosing a low-RTT sample reduces
queueing contamination, but cannot identify a fixed difference between outbound
and inbound network delay. See the primary specification,
[RFC 5905, section 8](https://www.rfc-editor.org/rfc/rfc5905.html#section-8).

There are limits to what the reference implements. BeatSync refreshes its clock
estimate but does not continuously change an already-playing source's rate to
correct independent audio-hardware drift. Its
`apps/client/src/lib/audioContextManager.ts:341` output-clock mapping helper has
no callers in this snapshot. It also exposes manual timing adjustment and
ignores reported output latency above 100 ms
(`apps/client/src/store/global.tsx:328`). Its README's millisecond claim is not a
measurement of CoSound or a guarantee for arbitrary computers and speakers.

## CoSound's adaptation

The existing authenticated WebSocket carries small clock exchanges alongside
state notifications. The client maintains a monotonic local clock and selects
the lowest-RTT offset from a six-second measurement window, refreshed every two
seconds after a faster startup sequence. Notifications continue to trigger the
existing REST refresh and local asset preparation.

The server persists `Player.playback_sync`, containing a common playback epoch
and the gain-transition timeline. Changed mixes receive a shared transition
time two seconds ahead and an eight-second fade. The previous gain envelope is
projected to the new transition time and those starting gains are retained, so
an update during a fade continues from the gain that the old timeline reaches
at the new transition. Connected instances retain their current envelope until
that boundary. All instances read the same timeline; starting a new process
does not reset the loops for players already running.

Each audio callback determines when its first output sample is expected to
reach the DAC, then reads the corresponding position in each loop. Fractional
phase correction keeps independent output clocks following the shared timeline.
Gain envelopes are evaluated against that same time, rather than against when
a WebSocket message arrived or a download completed. Downloads and conditioning
remain outside the audio callback. A late or reconnecting instance prepares the
assets and joins the current timeline. A newly started instance that receives a
still-pending transition waits for its boundary, rather than reconstructing the
superseded mix: up to the remaining two-second scheduling lead, in addition to
any time needed to acquire the clock and prepare assets. When the transition
is already underway, it joins at the current loop position and fade progress.

Asset conditioning uses a canonical 48 kHz rate before converting prepared
audio to the output device's rate. This keeps loop preparation consistent when
one device runs at 44.1 kHz and another at 48 kHz. Local spatial rendering,
reverb, channel routing, mute, and volume continue to operate on each machine.
If a newly requested asset cannot be prepared consistently, the existing mix
continues and a later refresh can retry; synchronized playback does not silently
substitute the unconditioned file. Unavailable previous-only assets do not block
joining a fully prepared target mix.

Vote confirmations also carry a shared playback deadline, half a second after
publication. Replicas choose the same note from the vote identifier. These
remain live notifications; votes missed while disconnected are not replayed.

The native timing primitive is `time.outputBufferDacTime`, the estimated DAC
time of the first sample of a callback buffer. It shares a stream clock with
`time.currentTime`; neither should be treated as a Unix timestamp. See
[PortAudio's callback time structure](https://files.portaudio.com/docs/v19-doxydocs/structPaStreamCallbackTimeInfo.html)
and [sounddevice's stream callback documentation](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html#sounddevice.Stream).
The existing meter timer periodically samples `stream.time` between two local
monotonic readings, outside the audio callback. It caches their correspondence
and discards slow samples. The callback maps its DAC timestamp through that
cached correspondence, so a delay acquiring Python execution does not move the
audio deadline. No PortAudio API call is added inside the callback.

This is an architectural adaptation written for CoSound's native looping mixer,
not a port of BeatSync's TypeScript application. BeatSync is credited as the
reference for server-clock estimation, future scheduling, and late joins. Its
supplied `LICENSE` is MIT, copyright 2025 freeman-jiang. No BeatSync source files
or third-party runtime have been incorporated into the player.

## Deployment

Deploy the server change and apply its database migration for
`Player.playback_sync` before rolling out the updated players. Use the existing
server release/migration process; do not point new application workers at a
database that has not received the migration. All backend instances serving the
same players must use the same database and have synchronized host clocks.

After the server is ready, update the player software on each participating
computer and launch it with the existing command and the same Player token.
The normal WebSocket endpoint and authentication are reused. See
[live player updates](realtime.md) for the existing ASGI, proxy, and Redis setup.
No new port, multicast service, or administrator timing configuration is needed.
For a playback comparison, update every participating instance: an old client
cannot participate in the new timing behavior.

The existing REST quota (`PLAYER_API_RATE`, default `120/m`) is shared by all
receivers using one Player token. Clock probes use WebSocket and do not consume
it. Size that quota for large installations and fallback polling frequency:
11 receivers polling every five seconds already make 132 REST requests/minute,
before connection refreshes and manifest requests. The usual 30-second fallback
uses substantially fewer requests; changing this quota is a deployment capacity
choice, not a synchronization setting.

The two-second lead is preparation headroom, not a promise that every cold
download completes in two seconds. Slow clients can join later at the correct
phase. Persistent network loss, audio underruns, suspended computers, and
unreliable output timestamps can still disrupt synchronization. Extra delay
inside Bluetooth links, wireless speakers, or downstream DSP may not appear in
the audio driver's timestamps. Begin validation with wired outputs.

A new synchronized instance waits for its first clock estimate before sounding.
If the driver cannot provide output timing, the status reports **output timing
unavailable** and synchronized audio waits. An established clock continues in
holdover during a network interruption and is refreshed after reconnecting;
holdover accuracy degrades with oscillator drift. A legacy server without the
timeline still uses the existing local playback path.

## Protocol and automated checks

`player.ready` advertises `sync_version: 1`. The client then sends
`player.time_ping` with `schema_version: 1`, an integer `id`, and monotonic
`client_send` seconds. The server returns `player.time_pong` with those fields
and Unix `server_receive`/`server_send` seconds. The client records receipt
locally. Eight startup probes run 150 ms apart, followed by a two-second
heartbeat. Three valid observations establish the initial estimate.

`/api/player` adds `playback_sync` with `version`, `revision`, `epoch`,
`effective_at`, `fade_seconds`, and `previous_layers` (`sound_id`/`gain` pairs).
The existing `layers` array contains the target gains. Timestamps use Unix
seconds; the epoch stays fixed while revisions identify new gain envelopes.
Vote notifications additionally carry `play_at` in Unix seconds.

Run the player checks from `src/player`:

```sh
PYTHONPATH=src uv run python -m unittest discover -s tests
```

The new tests cover clock offsets and jitter, an hour of simulated clock drift,
late joins, scheduled transitions, device latency, output rates, loop duration
rounding, callback timing, reconnection, chimes, and failed preparation. Server
coverage includes persistent timelines, interrupted fades, atomic rollback,
migration backfill, token isolation, and clock-probe authentication. Run the
server timing subset from the repository root:

```sh
src/server/.venv/bin/python src/server/src/main.py test app.test_player_websocket core.test_playback_sync core.test_player_events --noinput
```

These checks simulate clocks and audio callbacks; they do not open speakers.

## Measure on real devices

No multi-computer acoustic measurements or measured millisecond results are
claimed yet. Automated clock and rendering tests cannot establish end-to-end
accuracy for a particular installation.

1. Start two or three updated computers with the same Player token and backend.
   Use wired outputs and a common test sound containing a short pulse or impulse
   at known intervals, with enough silence to distinguish successive pulses.
   Keep the master levels low enough to avoid clipping. Use the same selected
   output channel and comparable rendering settings when comparing waveforms.
2. Record an output from every computer **simultaneously into separate channels
   of one recording interface**. Separate recordings have separate clock errors
   and cannot prove synchronization. Suitable line-level capture measures the
   electrical outputs; microphones also include acoustic travel time and room
   reflections. Keep microphone distances equal or measure their difference.
3. Cross-correlate matching pulse windows between recorded channels. Convert the
   peak's sample lag to milliseconds using `1000 * lag / recording_sample_rate`.
   Save the lag over time, its spread, the largest deviation, and any dropouts.
   Check the waveforms so periodic pulses, reverb, or different spatial filters
   do not produce a misleading correlation peak.
4. Repeat while joining a third player after playback has started, changing the
   mix during a fade, and reconnecting one player after a network interruption.
   Verify that it joins the current loop position and fade rather than replaying
   the beginning. Test both warm caches and a first download.
5. Keep the capture running for at least an hour to reveal clock drift. Include
   devices with different sample rates, realistic CPU activity, and the actual
   deployment network. Record each device, driver, output path, sample rate,
   network topology, and software revision with the results.

Listening across speakers remains useful, but the simultaneous recording is the
evidence for a millisecond claim. An installation's acceptable offset must be
checked against its measured output and acoustic paths, not inferred from a
successful WebSocket connection.
