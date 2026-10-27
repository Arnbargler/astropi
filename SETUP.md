# AstroPi — single-image recording milestone (2026-10-27)

## Verified and pending

Pi browser preview, colour/mono paths, and gain/exposure response are verified
on the actual SV705C. At 50ms: colour preview 14.8 FPS / RAW 15.8 FPS,
mono preview 16.6 FPS / RAW 16.5 FPS.

The one-shot USB file recorder passed simulated filesystem, format, API and
browser tests and **has now created files on the real Pi** in four separate
folders. All 11 real files passed size and SHA-256 checks against metadata.json;
independent FITS pixel/header interpretation still needs inspection. Timed sequences
and AM3N mount movement/GoTo/tracking are not implemented.

## Update and start the service

Stop the old Flask process with Ctrl+C, then run these commands on AstroPi:

    cd ~/astropi
    git pull --ff-only
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    python run.py --host 0.0.0.0 --port 8080

Visit http://astropi.local:8080/ (or the Pi LAN IP), hard refresh
Ctrl+Shift+R, Take Control and Start preview. This is still a LAN-only
development server, not a systemd service. Never expose it to the Internet.

## Single-image save operation

Choose a short exposure (start at 100ms) and gain (start 0), wait for SDK
Actual readbacks. In the **Save next camera frame** panel toggle any
combination of formats, then click **Capture & Save**. Defaults are FITS
and JPG selected; RAW16 and PNG optional. One button click uses the next
retrieved full-frame camera RAW16 buffer for all chosen files. No saving
happens automatically during ordinary preview.

The UI shows Waiting -> Saving -> Saved/Failed and lists generated paths.
Files are grouped in a timestamped folder under:
    /media/astropi-data/captures/

Example files in one group (only selected formats are generated):
    sv705c.raw16
    sv705c.fits
    sv705c.jpg
    sv705c.png
    metadata.json

## Format fidelity

- RAW16: exact 3856x2180 little-endian camera SDK bytes; 12-bit GRBG sensor
  values are shifted left four bits in a 16-bit container; no header.
- FITS: scientifically useful 3856x2180 12-bit GRBG Bayer mosaic stored
  unsigned via BITPIX=16 signed big-endian plus BZERO=32768 / BSCALE=1.
  Readers reconstruct physical values 0..4095. No debayer/stretch applied.
- JPG: colour quick-look only, 1928x1090 8-bit 2x2 GRBG superpixels; lossy.
- PNG: same quick-look at 1928x1090 8-bit colour but lossless compression.
  JPG/PNG use the selected auto/fixed stretch even if live Debayer is off.
  These are NOT high-resolution calibrated science data. Keep FITS/RAW16
  for scientific stacking and later processing.
- metadata.json: settings, sensor dimensions, UTC receipt time, Bayer format,
  file names, sizes and SHA-256 hashes.

FITS DATE-OBS is only an ESTIMATE: Pi UTC frame-receipt timestamp minus
configured exposure; the current SDK interface provides no sensor hardware
exposure-start timestamp. Pi has no RTC. Confirm UTC/NTP or manually verify
the clock for offline field captures. The camera may buffer frames across
setting changes, so SDK control readbacks are not calibrated timing proof.

## USB recording safety

Before accepting a job and again before each write/publish, AstroPi checks
that /media/astropi-data is a mounted, writable filesystem with EXACT UUID:
25b33cfa-b178-4b86-8a15-d00c8305cca5

The writer refuses recording when the USB is absent, wrong or low on space.
All write operations use directory file descriptors pinned to the mounted USB
device, not a blind pathname which might point to underlying microSD.
File data and directories are fsynced. A whole capture folder is published
atomically ONLY after all selected outputs and metadata are saved. If anything
fails in the middle, the directory remains explicitly named .partial and is
not reported as a completed exposure. Do not move/unplug USB during a save.

One image-save job at a time; saving happens in a separate worker thread and
continues after browser disconnect. Recording full exposure sequences is a
future milestone. The telescope is never moved by this version.

The user has already recorded FITS-only, FITS+JPG and all-four-format sets.
To inspect or further verify those files:

    ls -lah /media/astropi-data/captures/
    find /media/astropi-data/captures -maxdepth 2 -type f | tail -n 20

Real USB file-size and SHA-256 verification: 4/4 capture folders PASS,
11/11 files PASS (2026-10-27). Next: independently inspect FITS
headers/pixel values before treating the data as scientifically validated. Never intentionally unplug USB
during a save. Longer exposure sequences remain for subsequent development.
