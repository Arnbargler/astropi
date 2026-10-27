# AstroPi — counted exposure sequences (2026-10-27)

## Verification status

SV705C live preview, gain/exposure response and RAW/FITS/JPG/PNG single
capturing are verified on the Pi. Four real USB capture directories produced
11 image files; all 11 passed size and SHA-256 readback checks.

Counted **2–100-frame sequences and Cancel** are new, code-tested features
that still need their first real Raspberry Pi hardware test. A read-only
independent FITS/RAW16 Bayer pixel checker is also included; it passed
synthetic tests but has not yet checked the real files.

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

Use 5 frames, 100 ms exposure, gain 0, FITS+JPG only. Verify that progress
reaches 5/5 frames saved. On AstroPi inspect the newest folders:

    find /media/astropi-data/captures -mindepth 1 -maxdepth 1 -type d | tail -n 12

Then try a 10-frame sequence, optionally including RAW16 and PNG.
To test Cancel, try a 10-frame sequence and cancel after 2–3 saved.
Don't intentionally disconnect the USB stick during writing.

## Independent FITS/RAW pixel verification

Run this read-only check on the previously saved four-format exposure:

    python -m astropi.capture.verify /media/astropi-data/captures/20261027T212451_166770_6a75d1

This validates file lengths, SHA-256, FITS header dimensions, Bayer
metadata, 12-bit range and, when RAW16 is included, EVERY FITS pixel
against the original RAW16 data. No writes or SDK access.
