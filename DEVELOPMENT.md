# AstroPi — development handoff

**Read README → REQUIREMENTS → HARDWARE → DEVELOPMENT → SETUP.**
Code/tests establish implementation truth; requirements also include future work.
The user confirmed the three-tab UI works on the Pi on 2026-10-28.
**Next task: local VirtualSky in Find, not focus aids or GoTo.**

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
| `tests/`, `.github/workflows/tests.yml` | Fake-hardware Python tests and Node 22 browser regressions |

**GET routes:** `/`, `/api/status`, `/api/camera/progress`,
`/api/camera/frame.jpg`, `/api/capture/status`, `/api/mount/status`.

**POST routes:** `/api/control/{take,heartbeat,release}`,
`/api/camera/{start,stop,settings,binning,preview-mode,debayer}`,
`/api/capture`, `/api/capture/{sequence,cancel}`,
`/api/mount/{connect,disconnect,jog,jog-heartbeat,stop,environment/read}`.

**Absent:** `/atlas`, catalogue/search, GoTo, Home, Park, tracking
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
- **Find:** manual AM3N controls/status; VirtualSky placeholder only.
- **Fotograph (initial):** camera settings/preview, capture panel, USB and
  host status.
- Sticky global camera/mount/capture states and viewer-accessible
  `#mount-stop` remain visible on every tab. Operator token, 5 s lease
  heartbeat, capture state and Pi-owned jobs survive tab switches.
  Leaving Find with manual motion requests Stop; hidden Find cannot
  initiate a jog.

Browser polls camera progress every **50 ms** (while active), mount
status every **1 s**, full status every **3 s**; JPEG URLs are updated
only when frame number changes. **No WebSockets.**

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

## Next task: VirtualSky v0.1 inside Find (not yet installed)

The atlas is an **offline schematic pointing aid, not an image gallery**.
Keep it behind a replaceable adapter, embedded in the existing Find
tab; **do not add a separate Flask `/atlas` page** or introduce another
mount controller.

1. **Local dependencies:** pin an upstream VirtualSky revision; vendor
   `virtualsky`, stuQuery, planets/stars/constellations and
   Messier data under `astropi/static/`. Record license/attribution.
   No CDN, online lookups or photographic tiles. Avoid VirtualSky's
   online name-resolution `objects` mode.
2. **Time/site:** initialise chart at permanent +45.2933° /
   −75.8571° even without a mount connection. Obtain current **Pi UTC**
   from the existing `/api/status` response when Find opens, then
   advance the atlas clock and use the regular status polls to correct
   drift. **Do not add an atlas NTP check, status API, clock-accuracy
   warning or follow-up work for unsynchronized Pi time**; the operator
   explicitly chose to accept the Pi's clock indefinitely. If the
   AM3N is connected, optionally compare its *read-only* stored site,
   showing a location mismatch without modifying the mount.
3. **Chart UI:** chart occupies most of Find beside existing mount
   controls; pan/zoom, constellation lines/labels, horizon/cardinals,
   stars/planets and optional coordinate grids. Resize on tab reveal.
4. **Messier:** all **110** locally supplied objects; `M1`–`M110`
   search, clickable marker, centre and name/RA/Dec details. Verify
   click and object API on the pinned VirtualSky version. Absolutely
   **no mount movement** from chart interaction.
5. **Tests and field check:** Python and Node regressions, entirely
   offline page loads, correct Pi UTC usage and site coordinates
   (but no NTP warning), chart selection,
   responsive layout, tab/lease/capture persistence, viewer Stop and
   jog departure Stop. Check in a real Pi browser before marking as
   hardware verified.

**Deferred after atlas v0.1:** full OpenNGC NGC/IC database and
filter-independent search, reported mount marker, north/level and
two-star alignment, atlas-selected GoTo/tracking, focus zoom/HFR,
plate solving or stacking, manual time/site override.

## Testing / open verification

Run `python -m pytest -q` and `node --test tests/test_ui.cjs`;
GitHub Actions uses Python 3.13 and Node 22 on main and PRs.
Tab migration tests passed, and the user reports the Pi interface
functions as expected. This does **not** constitute fresh endurance,
serial-fault or telescope pointing verification.

Separate follow-ups: systemd service; long capture endurance; induced
USB/serial failures; FITS 2×2 `BAYERPAT` and metadata; 2×2 saved
quicklook colour. **Do not reopen atlas NTP/clock-accuracy work.**
Older experiments are in Git history, not instructions to re-enable
obsolete features.
