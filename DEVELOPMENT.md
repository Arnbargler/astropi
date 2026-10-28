# AstroPi development handoff

Read **README → REQUIREMENTS → HARDWARE → DEVELOPMENT**.
This is a working Pi application; the requirements also describe future
features. Treat Git history, not the current docs, as the troubleshooting log.

## Current code layout

| Module | Owner / responsibility |
| --- | --- |
| `run.py` | Flask foreground entry point (no systemd service yet) |
| `astropi/config.py`, `status.py` | hardware paths, USB presence, recording mount/UUID, Pi metrics; read-only status never opens devices |
| `astropi/control.py`, `web.py` | single operator token/lease, Flask API, worker state; no SDK or mount serial I/O on Flask request threads |
| `astropi/camera/sdk.py` | SVBONY SDK wrapper, camera enum/open/stream/restore/close, 1×/2× binning and post-bin ROI |
| `astropi/camera/worker.py` | sole camera SDK thread, separate one-slot JPEG preview worker; SDK frame buffer copied before recording. Reconfigure bin by closing/reopening a full SDK session in this same owner thread, never switching ROI mid-stream |
| `astropi/camera/preview.py` | disposable GRBG display preview + sparse stats |
| `astropi/capture/manager.py` | single shot or 2–200 counted-frame job, per-frame write boundary and cancellation, independent of browser |
| `astropi/capture/formats.py` | original RAW16, science FITS and colour quicklooks |
| `astropi/capture/storage.py` | USB UUID guard, space preflight, pinned directory-fd writes, fsync, atomic publication and SHA-256 manifest |
| `astropi/capture/verify.py` | retained read-only integrity/FITS pixel verifier, useful for regression and later field diagnostics |
| `astropi/mount/worker.py` | **only** serial owner: AM3N query, UTC sync on Connect, direction/speed whitelists, Stop and deadman |
| `astropi/templates/index.html`, `astropi/static/*` | browser UI, polling, pointer controls, captures and mount feedback |
| `tests/*`, `.github/workflows/tests.yml` | fake camera/USB/mount tests and Node browser regressions, run by GitHub Actions |

## Implemented Flask API

- `GET /api/status`, `/api/camera/progress`, `/api/camera/frame.jpg`,
  `/api/capture/status`, `/api/mount/status`.
- `POST /api/control/take`, `/heartbeat`, `/release`.
- `POST /api/camera/start`, `/stop`, `/settings`, `/binning`,
  `/preview-mode`, `/debayer`; `/api/capture`, `/api/capture/sequence`,
  `/api/capture/cancel`.
- `POST /api/mount/connect`, `/disconnect`, `/jog`,
  `/jog-heartbeat`, `/stop`, `/environment/read`.
  There is **no /api/mount/arm**, generic serial-command endpoint,
  GoTo, Home, Park, tracking or automatic site setter.

Gain presets in UI and worker are **0/50/100/260/350/450/550/650**. The
operator chose these values without requesting an SDK capability query.
Maintain the same whitelist in both places; high-gain behaviour awaits
physical verification on the SV705C.

The camera and mount workers are independent. Web poll routes read cached
state and image data; mount I/O must stay in one serial thread. Browser
camera preview uses polling, not WebSockets. The controls are for a
**trusted LAN** and token leases are coordination, not authentication.

## Invariants not to break

- The SVBONY SDK is initialized from real camera enumeration and opened
  once per streaming session. Do not interleave SDK calls across threads;
  camera preview can drop frames rather than accumulate unlimited work.
- Every output format of a saved frame derives from one immutable RAW16
  source. FITS retains 12-bit samples, with correct BZERO and byte order.
  1×1 is GRBG; Sony documents Bayer-preserving 2×2 binning, and the
  operator visually verified correct colours in the 2×2 preview on the
  physical SV705C (2026-10-28). JPG/PNG quicklooks use the same GRBG
  interpretation. Debayer Off generates monochrome preview and quicklooks.
  Binned FITS currently omits BAYERPAT because the writer has not been
  updated; do not claim this header is present without a code/test change.
  Recorded frames have SHA-256 manifest; incomplete writes remain unpublished.
- Never write recording data unless the **specific mounted USB UUID** is
  verified. Missing/incorrect USB must not fill the boot microSD.
  The Pi owns a recording after browser disconnect; crashing/rebooting the
  Python process does **not** resume a recording.
- AM3N Connect requires trusted NTP, UTC setters, ACKs and readback
  before claiming clock VERIFIED. Stored site is currently read-only.
- Movement uses whitelisted directions/rates, operator gating,
  press-and-hold and 600ms missing-heartbeat Stop; release/focus loss,
  operator release, intentional disconnect and viewer emergency Stop request
  Stop. Wait for stable reported axes before another jog; sending `:Q#`
  is not proof motors physically stopped. **No fixed jog time limit.**
- Never treat reported RA/Dec or Home as a sky-alignment solution.

## Browser layout: current vs next implementation

**Current:** `astropi/templates/index.html` and
`astropi/static/{app.js,style.css}` provide one full-width, responsive
dashboard with a live camera view, capture controls, camera settings and
manual mount controls. The compact capture controls use four format
checkboxes and **1/5/50/100/150/200/Cancel**, with Pi-owned sequences.
Preserve IDs, polling, controls, error/status feedback and the existing
camera/mount safety tests during migration.

**Next (approved; not yet in code):** one persistent HTML/JS browser app
with **Focus / Find / Fotograph** tabs; do **not** add the previously
suggested distinct `/atlas` Flask page. Keep a single shared connection,
operator token/heartbeat, camera and mount sessions, recording manager,
global status and accessible **STOP MOUNT**. Only the active view's
expensive rendering/polling needs to run; use care not to stop the backend
camera/recording while hiding a view. Explicitly Stop an active manual jog
on departure from Find; existing focus-loss and 600ms deadman are retained.

- **Focus:** shared preview now; click-to-centre zoom, peaking and HFR
  remain future features.
- **Find:** primarily VirtualSky with local chart controls and basic
  Messier target information; move existing mount controls here.
- **Fotograph:** existing preview, camera settings, capture and host/USB
  status. Do not change acquisition or recording semantics.

### Immediate work plan: offline VirtualSky v0.1 (not yet started)

1. **Tab shell:** refactor existing `/` into the persistent three-tab
   application, preserving operator ownership, camera/mount status,
   emergency Stop and recording progress. No independent page reloads.
2. **Vendor local VirtualSky:** add pinned upstream JS/data and required
   supporting assets under `astropi/static/`, retain license/attribution,
   and wrap its API behind a replaceable local JS adapter. No CDNs or
   external object lookup: the upstream `objects` option can perform an
   online lookUP when passed object names, so avoid that path.
3. **Site/time:** initialise the chart at the operator-confirmed **fixed
   permanent site +45.2933° N, −75.8571° east-positive**. Read/compare
   the AM3N's stored site when available; do not change mount site.
   Supply current **Pi UTC**, not an unverified client-clock assumption,
   and expose Pi NTP status. Show warnings if sync is absent or mount
   site conflicts; do not claim verified time/pointing without evidence.
4. **Chart controls:** offline stars/planets, constellations/labels,
   horizon/cardinals, draggable pan/zoom, and grid visibility. Ensure
   the chart resizes cleanly on tab activation and small screens.
5. **Messier aid:** load all **110** objects from local data with schematic
   markers. Implement simple `M1`–`M110` search and click/select
   information (name, RA, Dec) plus centre-on-target. Confirm the
   VirtualSky click callback/object lookup behaviour before connecting
   selection to a target: do not send any mount motion in v0.1.
6. **Test + handoff:** run Python and Node regressions; add tests for
   tab persistence, active-jog Stop on tab switch, global emergency
   Stop, offline asset loading/no remote URL, NTP/site warnings,
   Messier select/search and responsive layout. Update documentation
   only after the features are actually working.

**Deferred:** OpenNGC/NGC/IC full catalogue and filtered-object searching,
mount marker, sky alignment, atlas GoTo/tracking, custom focus aids,
image surveys/photos, and manual site/time override. No camera SDK
thread or mount serial protocol changes in the v0.1 atlas stage.

## Tests and outstanding verification

Run both `python -m pytest -q` and
`node --test tests/test_ui.cjs`. Workflow under
`.github/workflows/tests.yml` runs on main, feature/fix branches and PRs.
Mocks test SDK ownership, data conversion, USB fail-closed, sequences,
serial command gating, heartbeat Stop, NTP ACK/readback and UI behaviour.
Hardware-confirmed work is summarized in HARDWARE.md.

**Next priority:** implement the six-step **persistent tabs + offline
VirtualSky v0.1** plan above, then conduct real-Pi/browser field checks.
Keep mount GoTo/alignment and focus aids explicitly deferred.

**Other later work:** systemd startup/recovery; storage/USB failure and
long-running capture tests; 2×2 FITS `BAYERPAT` metadata (currently
absent) and optional saved quicklook/binned RAW-FITS parity regressions.
Do not enable competing USB/Wi-Fi mount controllers blindly.

Keep handoff documents concise; replace obsolete facts in place instead
of appending a new milestone diary. Do not remove safety regression tests
merely because the original failure has been fixed.
