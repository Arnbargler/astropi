# AstroPi

Pi-hosted observatory controller for **one SVBONY SV705C** camera and **one
ZWO AM3N** mount (Alt/Az). Browser UI on the trusted LAN; Raspberry Pi owns
acquisition, file writing, mount serial I/O and ongoing capture sequences.
The Linux desktop is a browser/development client, not a required server.

## Current state — verified 2026-10-28

- **Camera:** Full-frame 3856×2180, 12-bit GRBG in RAW16; live colour and
  monochrome preview, manual exposure and gain presets
  (0/50/100/260/350/450/550/650), fixed/auto preview stretch.
  **New: manufacturer-supported 1×1 and 2×2 hardware binning buttons below Gain,**
  with a fresh SDK session after change and bin-aware recording. 2×2 is
  Pi-verified for 2×2 RAW/FITS capture: the user saved ~4 MiB files and
  opened the FITS in Siril. **2×2 colour preview is now operator-verified
  visually correct with Debayer On; Debayer Off produces monochrome**.
  Sony's IMX585 documentation describes Bayer-preserving 2×2 binning;
  AstroPi uses GRBG for binned preview and JPG/PNG quicklooks. RAW16 and
  FITS pixel data remain unchanged.
  Measured 50 ms preview: ~14.8 colour / ~16.6 mono FPS at 1× on Pi.
- **Recording:** Individually selected RAW16, FITS, JPEG and PNG; one-shot
  or consecutive sequences up to 200 frames. USB-only storage guarded by
  filesystem UUID, SHA-256 manifest, fsync and atomic publication; no microSD
  fallback. On Pi: 11/11 saved-file hashes matched; FITS matched RAW16 at
  every sensor pixel. A 10-frame sequence completed and another cancelled
  cleanly at 4/10. Browser closure does not end an active Pi capture.
- **Mount:** AM3N firmware 1.8.8; serial Connect/Disconnect/Reconnect, model,
  reported Alt/Az and RA/Dec, status flags, date/time and stored site.
  Direct press-and-hold N/S/E/W controls (no separate Arm), release-to-Stop,
  five speed choices (8×, 20×, 60×, 720×, 1440×), prominent Stop,
  600 ms missed-jog-heartbeat timeout and settling checks. **No fixed
  duration limit.** E/N/S and slow-speed Stop were checked on the real mount;
  operator also reported speed selection and revised controls working.
  Exact angular rates and abnormal serial-loss Stop remain unverified.
- **Clock:** Every explicit mount Connect checks Pi NTP synchronization,
  writes UTC offset 0/date/time to the AM3N, requires setter ACKs and verifies
  clock readback. **Verified on actual AM3N**: mount date 10/28/26,
  UTC time 08:47:34, offset +00:00; site unchanged.
  "Mount time (UTC)" is *not* Ontario wall time.
- **Host:** Raspberry Pi 4B 4 GB, Debian 13 Trixie ARM64, Python 3.13.
  Camera SDK and USB storage are installed on the Pi (not in Git).

### Not implemented or not yet field-verified

**No sky alignment, astronomical GoTo, tracking, Park, offline star atlas,
plate solving, live stacking, fixed-interval sequence scheduling, or automatic
service startup.** Native mount Home was manually tested in earlier terminal
probes but **is not a browser action**. Mount RA/Dec are reported values, not
independently verified telescope pointing. The Pi has no RTC: sync requires
NTP, and manual field-time entry is a possible later feature. Extended
in-app recording endurance and deliberately induced USB/storage faults have
not been verified. We may later evaluate Stellarium control over AM3N Wi-Fi
or an INDI server, avoiding simultaneous conflicting USB/Wi-Fi commands.

## Interface: current dashboard and agreed next design

**Implemented (step 1, 2026-10-28):** one persistent browser application
with three tabs, **Focus / Find / Fotograph** (intentional spelling).
The original dashboard has been split into dedicated workspaces, with no
page navigation or new camera/mount sessions:

- **Focus:** the same live SV705C preview and camera settings as Fotograph;
  digital zoom and star-sharpness aids remain future work.
- **Find:** existing manual AM3N controls/status, alongside an explicit
  placeholder for the forthcoming offline VirtualSky atlas. No chart yet.
- **Fotograph (default tab):** existing full-frame preview, exposure/gain,
  binning/stretch/debayer, FITS/RAW16/JPG/PNG, capture buttons
  **1/5/50/100/150/200/Cancel**, image sequences and USB/host status.

The global sticky status strip displays camera/mount/capture state and
**STOP MOUNT** on all tabs, including for viewers. Existing preview and
settings elements are moved between Focus and Fotograph; they are not
duplicated. Tab changes preserve the operator lease, camera SDK session
and Pi-owned captures; leaving Find requests Stop on an active manual jog
and retains the mount's 600ms heartbeat failsafe. The underlying workers,
camera/frame APIs and recording system were not changed.

**Immediate next milestone (step 2):** Find tab with **fully local VirtualSky**,
no photographic imagery or network/CDN dependency, real-time local-sky
view using the permanent observing site +45.2933° N, −75.8571°
east-positive, Pi UTC/NTP status, stars/constellations/planets, horizon,
pan/zoom, grid controls, and **110 Messier targets** with local selection,
RA/Dec details and M-number search. Defer full OpenNGC, mount marker,
alignment, GoTo and tracking. See [DEVELOPMENT.md](DEVELOPMENT.md) for
the staged implementation plan.

On 2026-10-28 the operator confirmed correct SV705C 2×2 colours on real
hardware; the pending binned preview colour check is closed.

## Start / update

See [SETUP.md](SETUP.md) for install, launch, UI use and diagnostics.
On the Pi, with existing Flask stopped:

```bash
cd ~/astropi
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python run.py --host 0.0.0.0 --port 8080
```

Open http://astropi.local:8080/ and hard-refresh after changes.
Run the camera and mount **independently**; no mount movement is sent at
startup. The Flask development server is LAN-only, **not Internet-facing**.

## Repository orientation (for the next development session)

1. **README.md** — current verified status and non-features.
2. **REQUIREMENTS.md** — selected feature IDs and scope decisions.
3. **HARDWARE.md** — hardware, paths, protocol, verified quirks and limits.
4. **DEVELOPMENT.md** — actual code ownership, test strategy and next work.
5. **SETUP.md** — operational commands and troubleshooting.

Source: `astropi/camera/` SDK + preview worker;
`astropi/capture/` science formats, UUID-safe USB writer and independent verifier;
`astropi/mount/worker.py` sole mount serial owner;
`astropi/web.py` Flask API and operator lease;
`astropi/static/` + `templates/` browser UI;
`tests/` fake-hardware and browser regressions. CI tests Python and Node.

**Preserve:** single SDK owner, single mount serial owner, immutable RAW16
source, verified USB UUID with no microSD fallback, operator-gated motion,
release/heartbeat Stop and honest status on unsuccessful mount time sync.
Do not infer a feature is implemented merely because it appears in
requirements or was explored in a standalone terminal probe.

Detailed historical hardware experiments and superseded setup instructions
remain in Git history (not in the current handoff); start with the current
documents instead.
