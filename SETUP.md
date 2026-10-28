# AstroPi — counted exposure sequences (2026-10-27)

## Current AM3N manual controls

Press and hold any direction button immediately once **Take Control** and
**Connect Mount** have succeeded; there is **no separate Arm step**.
Release to stop. Slow 8×, Medium 20×, Fast 60×, Slew 720× and Max 1440×
are available; the last two need verification on the real AM3N. Fixed
duration caps are removed. Emergency Stop and the independent 600ms
lost-heartbeat timeout are unchanged. The serial owner waits for mount
position to settle before accepting another jog. Speed defaults to Slow
on reconnect.

Historic manual jog tests and their old Arm/3s instructions later in
this file are retained for reference; **use these current instructions**.

## Verification status

SV705C live preview, gain/exposure response and RAW/FITS/JPG/PNG single
capturing are verified on the Pi. Four real USB capture directories produced
11 image files; all 11 passed size and SHA-256 readback checks.

**Five-frame and ten-frame sequences have completed on the real Pi.** A
separate ten-frame sequence was safely cancelled with **4/10 saved**, four
contiguously numbered frame folders and **zero .partial directories**.
Extended endurance and simulated/real USB-failure recovery remain unverified. The independent FITS/RAW16
checker passed against a real previously saved four-format camera capture:
all four file size/hash checks passed, FITS structure and 12-bit range passed,
and every FITS Bayer pixel matched the corresponding RAW16 sensor value.

Low-speed manual mount jog and Stop have been added and E/N/S directions
are user-verified. No Home/GoTo, sky tracking, plate solving or fixed-interval
sequence scheduling has been added. The camera SDK stream remains continuous.

## Install

Stop the old Flask app with Ctrl+C. On the Pi:

    cd ~/astropi
    git pull --ff-only
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    python run.py --host 0.0.0.0 --port 8080

Open http://astropi.local:8080/ on the trusted LAN, hard-refresh using
Ctrl+Shift+R, Take Control, then Start preview.

## Sequence controls

1. Choose exposure and gain from the existing radio-style presets. Wait for
   their Actual SDK readbacks before starting a sequence.
2. Check FITS/RAW16/JPG/PNG independently. FITS and JPG default selected.
3. Set Frames in sequence to a whole number from **2 to 100** (default 10).
4. Click Start Sequence and monitor "completed / requested" frames.
5. Cancel Sequence stops at the next safe frame boundary. If a file is
   being written, that frame is allowed to finish and sync first.
6. Capture & Save remains a separate **single-frame** button.

The Pi saves one full-resolution RAW16 sensor frame at a time. All selected
formats for that frame come from the SAME source buffer; the next source
frame is not accepted until the disk writer has finished. The SDK never
restarts between exposures. Exposure, gain and the saved JPG/PNG stretch
are frozen throughout each sequence; changing exposure/gain is rejected.

Each sequence frame gets its own timestamped folder under:

    /media/astropi-data/captures/

The folder contains only the selected formats plus metadata.json. Its
"sequence" metadata includes the common job ID, 1-based frame index, and
total requested count; completed frame folders are listed in the UI.
Each frame has SHA-256 checksums and a UTC receipt timestamp; FITS start
time is estimated because the camera SDK supplies no sensor timestamp.

**USB safety:** The Pi verifies the exact mounted recording UUID and
sufficient estimated space for the ENTIRE requested sequence before
acceptance, and verifies the USB again for every saved frame. Each completed
directory is published atomically; incomplete writes remain .partial.
There is NO fallback to the Pi's microSD card. The operation ends with a
reported error if the drive fails or becomes full during recording.

**Browser independence:** A recording continues on the Pi if the controlling
browser reloads or disconnects. Do not restart/kill the Flask/Python process
mid-sequence; service crashes/reboots do not resume a sequence automatically.
Camera Stop terminates the sequence (possibly after an in-flight frame).
Long exposures up to 30 seconds can delay cancellation or Stop until the
SDK's current exposure/wait returns.

**Timing:** Sequence cadence is as fast as exposure, readout and the
selected file formats allow. It is NOT a fixed-second interval scheduler.

## First hardware test

**Completed:** the Pi reported 5/5 frames saved and five separate folders
for the five-frame FITS+JPG run. To inspect the latest folders:

    find /media/astropi-data/captures -mindepth 1 -maxdepth 1 -type d | tail -n 12

**Completed on Pi:** 10/10 normal sequence (ID 77f0893f415b) and 4/10
cancelled sequence (ID 62b28bdbfabd). Frame numbering contiguous and zero
incomplete folders. Next check these sequence frames' file-size/SHA-256
checksums, optional all-format recording, and longer endurance/fault handling.
Don't intentionally disconnect the USB stick during writing.

## Independent FITS/RAW pixel verification

Run this read-only check on the previously saved four-format exposure:

    python -m astropi.capture.verify /media/astropi-data/captures/20261027T212451_166770_6a75d1

**Passed on Pi for this precise capture:** 4 file sizes/checksums PASS,
FITS structure and 12-bit range PASS, and every Bayer pixel matched RAW16.
The verifier remains read-only; no writes or SDK access.


## First read-only AM3N mount connection (new; Pi hardware retest pending)

Mount USB by-id serial path:
    /dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00

On the Pi, install updated requirements before launching. The new dependency
is pyserial 3.5. After updating, start AstroPi as usual (commands above).
No mount connection is attempted automatically on Flask start or page load.

1. Connect and power the ZWO AM3N normally, with the hand controller/mount
   physically stationary and clear. Do NOT send a Home command.
2. In the browser click **Take Control**, then **Connect Mount** inside
   the ZWO AM3N panel. Camera preview does not need to be running.
3. Look for Connection: connected; Model AM3N and firmware 1.8.8; live
   reported Altitude, Azimuth, RA, Dec, raw :GU# status, and timestamp.
4. Click **Disconnect**. Verify the panel returns to "disconnected",
   coordinates clear to dashes, and camera preview/capture is unaffected.
5. Click **Connect Mount** again to test clean reopening. If the by-id
   alias is absent or any serial response fails, the mount panel displays
   the error and clears stale positions. Explicit Connect is required
   after device recovery.

This milestone ONLY sends the following **read-only** serial queries:
    :GVP# :GV# :GU# :GA# :GZ# :GR# :GD#

There is no Move, slew, Home, Park, GoTo, tracking or clock/site update
control in this version. Mount RA/Dec are reported estimates; no verified
sky alignment exists. The worker deliberately does not write time/site:
Pi lacks an RTC and offline trusted-time initialization is unresolved.
No general-purpose serial-command endpoint is exposed.

For a quick terminal diagnostic (no mount modification), while the app is
running:

    curl -s http://127.0.0.1:8080/api/mount/status | python3 -m json.tool

If the connection fails, provide that output and the current UI error
before we add ANY controls that could move the mount. Do not launch a
second serial-monitor process against the same mount port simultaneously.


## AM3N first Pi read-only status verified (2026-10-27)

User screenshot confirmed **USB detected**, **serial alias available**,
**Connection: connected**, model **AM3N** firmware **1.8.8**,
altitude **+00*00:00**, azimuth **000*00:00**, reported
RA **13:13:45** and Dec **+44*42:24**.
Mount raw `:GU#` was `nNZM0000000000`: not tracking, not
slewing, with Alt/Az marker `Z`. This differs from earlier
`nNHZM040400990` by having no `H` flag. The original code
incorrectly assumed `Z` was at one fixed position, displaying the
mode as unknown. Code now recognizes known optional flags by presence
before the `M` suffix; this parser correction awaits Pi redeployment.

**Pi hardware test passed:** screenshots show Connect (AM3N 1.8.8, live
Alt/Az and reported RA/Dec, `nNZM...` decoded Alt/Az), Disconnect
(position and timestamp cleared), and Connect again (position restored).
The mount remained in the stationary zero-altitude/azimuth reported state.
This proves intentional browser connection lifecycle; it does NOT verify
forced USB-loss safety or any motion controls. Those remain separate gates.


## First AM3N manual Stop and short-jog trial (E direction now Pi-verified)

First Pi motion screenshot pair (2026-10-27): azimuth was reported as
000°00′00″ before and 000°05′57″ afterward, with unchanged altitude
+00°17′26″. Both panels displayed `Reported axes stable after Stop`.
That first screenshot pair showed real manual movement and reported settling.
After reboot, the user completed a controlled E-jog/release trial and confirmed
that movement and stopping behaved as expected. No exact measured travel or
hold time was supplied for the isolated test; North and South jog/release were subsequently reported working on the real
mount at the deliberately slow R5 speed. West and 600ms missed-heartbeat expiry remain unverified. The independent
3s hard jog cutoff was verified on the physical AM3N: the operator held
a direction and saw Stop requested, then observed automatic stopping. The observed 5′57″ is approximately 3s at the
previously tested ~2′/s R5 rate; confirm the hold time before further tests.

This is a **controlled movement trial**. Keep cables, cameras and people
clear of the path. Have the mount's physical Cancel or a safe 12V power
cutoff immediately accessible. Do not deliberately pull USB or kill Python
while moving; the software cannot guarantee a Stop when communications die.

1. Update AstroPi and run Python and browser tests; stop/restart Flask
   only while the mount is stationary, then hard refresh the browser.
2. Take Control and Connect Mount. Confirm fresh altitude and azimuth.
3. **Click the prominent STOP MOUNT button BEFORE moving anything.**
   Expect "Stop requested" then "Reported axes stable after Stop".
   If it shows uncertain/errors, DO NOT arm or move; provide diagnostics.
4. With physical Stop at hand, click **Enable one low-speed jog**, then
   press and hold **E** for only ~0.3–0.5 seconds and release.
   The mount should move a small amount and then stop; wait for reported
   position stability. Small additional movement after Stop may occur.
5. One jog requires one explicit arm. No second direction, longer jog,
   deliberate network loss or cable-unplug test until this first test
   passes. Each jog has a Pi-enforced 600ms missing-heartbeat deadline
   and a 3-second absolute maximum, but neither is fail-safe against
   severed USB or crashed hardware.
6. Send the visible status, or run this read-only diagnostic:

       curl -s http://127.0.0.1:8080/api/mount/status | python3 -m json.tool

Only rate `:R5#`, manual `:Mn#/:Ms#/:Me#/:Mw#`, and Stop `:Q#`
are available in this milestone. No automated Home, GoTo or tracking.


## New manual speed choices — on-Pi testing pending

The manual mount panel now offers radio-style speed choices:

- **Slow 8×**: `:R5#` — previously verified on real AM3N; max 3s/jog.
- **Medium 20×**: `:Rv20.00#` — new selection; max 2s/jog.
- **Fast 60×**: `:Rv60.00#` — new selection; max 1s/jog.

All options have the same **600ms missing-heartbeat Stop**, one-jog arming,
operator permissions and viewer emergency Stop. Every jog first sends
the verified `:R5#` baseline to avoid inheriting an arbitrary old speed.
Medium/Fast are rate requests, **not hardware-verified accurate speeds**.
Reconnecting the mount resets the selection to Slow. Changing speed during
an armed/active jog is disabled.

After deployment, do NOT jump directly to Fast. With cables and mount clear,
physical Cancel/power cutoff in hand and mounted load secure, first confirm
Slow still stops normally. Then try **one short Medium/East press ~0.3s**,
release and wait for stable coordinates. Stop immediately if behaviour differs.
Only after this is confirmed should Fast be considered, with an even shorter
test press. Longer 20×/60× travel, emergency failures or severed USB are
NOT safe to simulate casually. Document any actual angular change and stop
latency. No GoTo, Home or tracking added.
