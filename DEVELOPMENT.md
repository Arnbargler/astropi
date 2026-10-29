# AstroPi — development handoff

**Read README → REQUIREMENTS → HARDWARE → DEVELOPMENT → SETUP.**
Code/tests establish implementation truth; requirements also include future work.
The user confirmed the three-tab UI works on the Pi on 2026-10-28.
**Current task: offline VirtualSky in Find is implemented; field-check it on the Pi before advancing to focus aids or GoTo.**

## Code map

| Source | Responsibility |
| --- | --- |
| `run.py`, `astropi/web.py`, `control.py` | Foreground Flask; routes and 15-second single-operator lease; viewer Stop |
| `astropi/config.py`, `status.py` | Paths, USB/host state and Pi UTC; atlas reuses `/api/status` UTC without a new time endpoint |
| `astropi/camera/sdk.py`, `worker.py` | SVBONY ctypes; sole SDK thread, acquisition, settings, binning session restart, one-slot preview mailbox |
| `astropi/camera/preview.py` | JPEG colour/mono, stretches, sparse raw statistics |
| `astropi/capture/{manager,formats,storage,verify}.py` | Pi-owned jobs, science/quicklook formats, UUID-safe writes, read-only integrity verification |
| `astropi/mount/worker.py` | Sole AM3N serial worker: telemetry, verified UTC sync, manual jog/Stop/deadman |
| `astropi/templates/index.html`, `astropi/static/{app.js,style.css}` | Persistent Focus/Find/Fotograph UI |
| `astropi/static/atlas.js`, `astropi/static/vendor/virtualsky/` | Offline VirtualSky adapter and pinned catalogue/scripts |
| `tests/`, `.github/workflows/tests.yml` | Fake-hardware Python tests and Node 22 browser regressions |

**GET routes:** `/`, `/api/status`, `/api/camera/progress`,
`/api/camera/frame.jpg`, `/api/camera/diagnostics`,
`/api/capture/status`, `/api/mount/status`.

**POST routes:** `/api/control/{take,heartbeat,release}`,
`/api/camera/{start,stop,settings,binning,preview-mode,debayer}`,
`/api/capture`, `/api/capture/{sequence,cancel}`,
`/api/mount/{connect,disconnect,jog,jog-heartbeat,stop,environment/read}`.

**Absent:** `/atlas`, full OpenNGC search, GoTo, Home, Park, tracking
and arbitrary serial-command endpoints. **No separate atlas time/NTP
endpoint is needed**; `/api/status` already includes Pi UTC.

## Persistent browser UI — implemented and Pi-checked

One document at `/`. `activateTab` in `app.js` shows/hides
**Focus / Find / Fotograph**. The **same**
`#shared-preview-card` and `#shared-camera-controls` DOM nodes are
relocated between Focus and Fotograph. Do not clone their IDs, duplicate
the JPEG preview stream, or navigate/reload on tab selection.

- **Focus:** camera preview/settings; zoom and star focus measurements
  are not built.
- **Find:** full-width offline VirtualSky chart, 110 Messier markers/search and read-only target selection. The shared mount controls are *not* in this tab.
- **Fotograph (initial):** camera settings/preview, capture panel, USB and
  host status.
- **Shared mount overlay drawer:** `#mount-drawer` is one actual AM3N
  card, outside every `role=tabpanel`, opened by sticky
  `#mount-drawer-toggle` in any workspace. JS `setMountDrawer()`
  toggles `inert`, `aria-hidden` and slide CSS; `positionMountDrawer()`
  keeps its top immediately below the sticky status strip (including
  wrapped alerts). It overlays rather than resizes tab content; the drawer
  stays open across tab switches. No pin/dock mode in this version.
- Sticky global camera/mount/capture states and viewer-accessible
  `#mount-stop` have higher stacking order and remain accessible with
  drawer open or closed. Operator token, 5 s lease heartbeat, capture
  state and Pi-owned jobs survive tab switches.
  Closing the drawer or changing workspaces during a jog requests Stop
  **before any subsequent jog**; closed/inert drawer prevents jog starts
  in all tabs. Switching workspaces/closing the drawer when idle does
  not send Stop. Retain pointer release/blur/visibility/pagehide Stop,
  600 ms server deadman and physical Cancel/power warning.

Browser polls camera progress every **50 ms** (while active), mount
status every **1 s**, full status every **3 s**. The **stage-1 browser
preview loader** in `app.js` keeps two `<img>` elements inside the
**single relocated** preview card and allows only **one outstanding JPEG
request**. The currently visible JPEG stays on screen until its alternate
element's `load` event; intermediate camera frame numbers are skipped
and the newest available frame is requested afterward. Errors and a
**2 s load timeout** release the request; closing/reopening the camera
invalidates stale image callbacks. This changes only browser delivery,
**not** SDK acquisition, preview conversion, FPS, camera polling rate, or
the mount/lease/deadman path. No extra image stream or HTTP fetch.
**No WebSockets.** Camera UI replies from `/api/status` and
`/api/camera/progress` carry a browser-local request sequence. A response
to an older-started request that returns after a newer response has
already been applied is **ignored for camera state and JPEG updates**.
This prevents stale frame-number rollbacks or stale stopped/connecting
status from hiding a running preview. Genuine new camera sessions still
reset the loader when current data has no frame or a lower frame number.
Regression tests deliberately delay full-status responses. Operator
reports some stutters after stage 1; this is a targeted logic correction,
not proof that all pauses were caused by out-of-order replies.

## Intermittent preview pauses — Stage 2 diagnostics (implemented, Pi test pending)

**Observation:** Browser preview and Flask access-log traffic still sometimes
pause even after stage-1 JPEG serialization; user disconnected AM3N and
confirmed that intercepting ~33 `/api/mount/status` requests in ~30 s
did not eliminate pauses. The HTTP mount-status endpoint is a cached dict
read; the mount serial worker was disconnected. Do not blame mount polling.

Read-only `GET /api/camera/diagnostics` returns in-memory counters **without
touching the camera SDK**: `raw_frames` (successful SDK acquisitions),
`jpeg_frames` (completed preview conversions), `raw_age_ms` /
`jpeg_age_ms`, currently active `sdk_inflight_ms` /
`jpeg_busy_ms`, last/max SDK-return interval and wait time, last/max
JPEG-completion interval and processing duration. It retains **up to 32
recent outliers** (`sdk_gap`, `jpeg_gap`, `jpeg_slow`,
`sdk_timeout_11`) tagged with UTC, exposure and frame counts. The
threshold for gap events is max(0.65 s, 1.75 × exposure + 0.2 s);
JPEG processing >500 ms logs a slow event. This avoids classifying a
deliberate multi-second exposure as an abnormal gap. The counter history
resets with a fresh camera session; this does NOT change SDK calls,
exposure settings, threading, JPEG buffering or browser polling.

From the Pi with the camera preview running:
`curl -s http://127.0.0.1:8080/api/camera/diagnostics | python3 -m json.tool`
Run after several visible stutters; compare SDK gaps vs JPEG gaps.
If both remain short despite browser freezes, investigate HTTP scheduling,
Werkzeug per-request terminal logging, 3-second `/api/status` system
checks, browser requests and networking. The Flask access log timestamps
completed requests, not request issuance. A long in-progress SDK wait
can also be observed via `sdk_inflight_ms`, while an in-progress JPEG
render shows `jpeg_busy_ms`; long exposures naturally increase SDK
wait and frame ages.

## Must-preserve invariants

1. **Camera SDK:** one worker owns all SDK calls. Open by real
   enumeration/CameraID; one continuous capture stream per SDK session.
   Switching 1×1 ↔ 2×2 binning requires close/reopen, not a video
   stop/start in the same session (previously caused SDK error 11).
   Set exposure **before** gain. Exposure presets 1 ms–30 s; gain
   whitelist **0/50/100/260/350/450/550/650** in both JS and Python.
   Operator observed expected gain response; the actual SDK maximum
   and HCG threshold have not been measured.
2. **RAW/science:** one immutable SDK RAW16 buffer copy per frame.
   12-bit GRBG values are left-shifted four bits in little-endian RAW16.
   FITS stores 12-bit ADU with big-endian `BITPIX=16`,
   `BSCALE=1`, `BZERO=32768`. User visually verified the
   **2×2 preview colours**; saved JPG/PNG colour at 2×2 was not separately
   field-checked. **2×2 FITS still omits `BAYERPAT`**, the verifier
   expects omission, and the manifest still says
   `"unverified at 2x2"`. Changing metadata requires a separate
   code/test change; it is not a remaining *preview* colour problem.
3. **Capture/storage:** only the specified mounted USB UUID is valid.
   Preflight and recheck throughout write; pinned directory-fd, fsync,
   SHA-256 and atomic `.partial` publication. **Never fall back to
   OS microSD**. Jobs (up to 200 frames) are Pi-owned; the writer
   finishes each save before another RAW frame is accepted.
   Browser closure doesn't cancel jobs; process death/reboot does not
   resume them. Settings locked during an active sequence.
4. **Mount safety:** one serial owner, whitelisted directions/rates,
   operator gating for motion, viewer emergency Stop. Hold-to-move and
   release/blur/tab departure Stop, server **600 ms** deadman,
   post-Stop reported-axis stability. No arbitrary 3-second cutoff.
   A sent `:Q#` is not proof motors stopped; physical Cancel/power
   is the final fallback.
5. **Time and site:** explicit AM3N Connect requires verified Pi NTP
   to sync UTC offset/date/time with ACKs/readback; failure is honestly
   displayed and does not forbid *manual* jogging. **Do not change this
   existing mount behaviour while implementing the atlas**; the decision
   to skip atlas clock validation is separate. The mount-stored
   permanent site is **+45.2933° N, −75.8571° east-positive**.
   **Never silently overwrite it.** The Pi has no RTC. Reported RA/Dec
   and mount Home do not establish optical sky alignment.
   Never auto-Home, GoTo, slew or track when opening AstroPi.

## Offline VirtualSky v0.1 in Find — now implemented

The first atlas is **locally packaged**; it does not add Flask `/atlas`
or any mount command API. All sky rendering is confined to
`astropi/static/atlas.js`, a replaceable adapter loaded alongside
`app.js`. The Find panel's placeholder was replaced by an offline sky
chart, Messier search, horizon/detail controls and toggles. Vendor files
are pinned to upstream tree `271c801d6504d1c478bc0c64dce4938399749c69`
(virtualsky 0.7.7), with provenance/permission notes beside the files.
The local library loads `stars.json`, `lines_latin.json`, `lang/en.json`
and the local planet ephemeris plugin. All 110 Messier targets are
supplied by local `messier.json`; each pointer uses custom **text-only
HTML**, preventing VirtualSky's default remote Wikisky links/images.
Do not enable its remote object name-resolution mode.

**Time/site:** fixed **+45.2933° N / −75.8571° longitude
east-positive**, including before mount Connect. Fetch existing
`/api/status.utc` when Find is entered; the adapter advances Pi UTC
locally and corrects the clock on periodic full-status polls. **Never
introduce atlas NTP verification or warning**; Pi clock is accepted
indefinitely by operator decision. Existing separate AM3N Connect-time
NTP check remains unchanged. The atlas does not modify mount site.

**Interactions:** polar horizon/cardinal view with pan, and zoomable
gnomic detail view. Search M1–M110 or click a local marker to centre
and show name, RA and Dec; constellation line/label and equatorial grid
toggles. Target selection is informational; **no GoTo, tracking,
alignment, Home/Park or motion API calls**. On Find reveal call
`resize()`, keeping the chart inside the persistent DOM. Do not clone
camera preview/settings nodes. Global Stop and jog-on-tab-departure
Stop remain untouched.

**Verification:** `tests/test_atlas.py` checks local assets, all 110
catalogue entries and motion-free adapter. `tests/test_atlas.cjs`
checks Pi UTC, search/clicks, projections and offline loading;
`tests/test_ui.cjs` covers retained tab safety and atlas DOM. CI success does not imply
a real-Pi rendering test: verify offline loading and chart dragging,
M1/M31/M42/M110, no remote requests, UTC, responsive layout, mount
Stop, and unbroken capture/lease continuity on the actual Pi.

**Deferred:** OpenNGC NGC/IC catalogue and filter-independent search,
read-only mount marker, north/level and two-star alignment,
atlas-selected GoTo/tracking, focus zoom/HFR, plate solving, stacking,
manual time/site override.

## Testing / open verification

Run `python -m pytest -q` and `node --test tests/test_ui.cjs`;
GitHub Actions uses Python 3.13 and Node 22 on main and PRs.
Tab migration tests passed, and the user reports the Pi interface
functions as expected. This does **not** constitute fresh endurance,
serial-fault or telescope pointing verification.

Separate follow-ups: real-Pi atlas browser verification; systemd service; long capture endurance; induced
USB/serial failures; FITS 2×2 `BAYERPAT` and metadata; 2×2 saved
quicklook colour. **Do not reopen atlas NTP/clock-accuracy work.**
Older experiments are in Git history, not instructions to re-enable
obsolete features.
