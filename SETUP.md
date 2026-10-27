# AstroPi — counted exposure sequences (2026-10-27)

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

No mount movement, tracking, plate solving or fixed-interval sequence
scheduling has been added. The camera SDK stream remains continuous.

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
