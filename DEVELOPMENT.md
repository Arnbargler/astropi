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

## Browser layout

The capture strip uses four accessible native checkbox toggles and fixed
count buttons **1/5/50/100/150/200**, plus Cancel. Browser sequences POST
`/api/capture/sequence`, one shot POSTs `/api/capture`. Both retain the
existing capture job, USB space preflight, operator lease and cancel-at-write-
boundary semantics. A sequence is capped at 200 frames. Don't change the
camera SDK ROI or reduce the capture resolution in order to save UI space.

The dashboard uses `astropi/templates/index.html` and
`astropi/static/style.css`. The `.dashboard-grid` is three fluid columns
near **1920×1080**: an imaging column (preview, capture, Pi/storage status),
camera settings, then mount. Breakpoints: at 1550px use two columns,
at 920px stack panels, retaining camera settings before recording.
Avoid reinstating the old 1140px shell width or instructional prose; keep
state and safety messages and existing DOM IDs. No JavaScript layout changes
or hardware-control timing changes are intended in this iteration.

## Tests and outstanding verification

Run both `python -m pytest -q` and
`node --test tests/test_ui.cjs`. Workflow under
`.github/workflows/tests.yml` runs on main, feature/fix branches and PRs.
Mocks test SDK ownership, data conversion, USB fail-closed, sequences,
serial command gating, heartbeat Stop, NTP ACK/readback and UI behaviour.
Hardware-confirmed work is summarized in HARDWARE.md.

Suggested next steps **after the operator tests this cleanup**:

1. Discuss mount GoTo/sky-alignment architecture, including external
   Stellarium/INDI or AM3N Wi-Fi instead of duplicating a planetarium.
   Do not enable competing USB and Wi-Fi movement controllers blindly.
2. Systemd startup/recovery and longer camera/storage error/endurance tests.
3. **2×2 colour is verified in preview**: the operator confirmed correct
   colour rendition on the real SV705C on 2026-10-28. The earlier pending
   red/blue preview check is closed. The FITS writer still omits BAYERPAT
   at 2×2; adding it would be a separate code/test change. Optional
   field regressions include saved JPG/PNG colours, 2×2 Debayer Off,
   RAW16/FITS parity and sequence Debayer freezing. Future arbitrary ROI,
   offline sky atlas, manual alignment, focus tools and field time entry
   remain deferred.

Keep handoff documents concise; replace obsolete facts in place instead
of appending a new milestone diary. Do not remove safety regression tests
merely because the original failure has been fixed.
