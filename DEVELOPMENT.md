# AstroPi — development handoff

**Read README → REQUIREMENTS → HARDWARE → DEVELOPMENT → SETUP.**
Code/tests establish implementation truth; requirements also include future work.
The user confirmed the three-tab UI works on the Pi on 2026-10-28.
**Current state: AM3N GoTo (M40) and emergency Stop (M45) were field-tested; native tracking ON/OFF and status were field-tested. North/Level physical setup confirmation is implemented as an operator checkpoint; two-star/optical alignment remains unimplemented.**

## Code map

| Source | Responsibility |
| --- | --- |
| `run.py`, `astropi/web.py`, `control.py` | Foreground Flask; routes and 15-second single-operator lease; viewer Stop |
| `astropi/config.py`, `status.py` | Paths, USB/host state and Pi UTC; atlas reuses `/api/status` UTC without a new time endpoint |
| `astropi/camera/sdk.py`, `worker.py` | SVBONY ctypes; sole SDK thread, acquisition, settings, binning session restart, one-slot preview mailbox |
| `astropi/camera/preview.py` | JPEG colour/mono, stretches, sparse raw statistics |
| `astropi/capture/{manager,formats,storage,verify}.py` | Pi-owned jobs, science/quicklook formats, UUID-safe writes, read-only integrity verification |
| `astropi/mount/{worker,goto}.py` | Sole AM3N serial worker: telemetry, verified UTC+permanent site sync, jog/deadman, catalogue-only native GoTo, Stop and coordinate precession |
| `astropi/templates/index.html`, `astropi/static/{app.js,style.css}` | Persistent Focus/Find/Fotograph UI |
| `astropi/static/atlas.js`, `astropi/static/coordinates.js`, `astropi/static/vendor/virtualsky/` | Offline VirtualSky adapter, J2000→date geometric Alt/Az/visibility and pinned catalogue/scripts |
| `tests/`, `.github/workflows/tests.yml` | Fake-hardware Python tests and Node 22 browser regressions |

**GET routes:** `/`, `/api/status`, `/api/camera/progress`,
`/api/camera/frame.jpg`, `/api/capture/status`, `/api/mount/status`.

**POST routes:** `/api/control/{take,heartbeat,release}`,
`/api/camera/{start,stop,settings,binning,preview-mode,debayer}`,
`/api/capture`, `/api/capture/{sequence,cancel}`,
`/api/mount/{connect,disconnect,jog,jog-heartbeat,stop,environment/read,environment/sync,goto,tracking,north-level}`.

**Absent:** `/atlas`, full OpenNGC search, Home, Park,
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
- **Find:** offline VirtualSky, 110 Messier markers/search, geometric Alt/Az/visibility, and a separate GoTo button enabled only for the controller on a ready, NTP-verified idle mount. No auto-GoTo on selection or tab entry.
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

Browser polls camera progress every **50 ms** while active, mount
status every **1 s**, full status every **3 s**. `app.js` uses two
alternating `<img>` elements in the one relocated preview card. Only
one JPEG load can be outstanding; keep the previous successful frame
visible, skip superseded frames and release failed loads after 2 s.
Camera sessions invalidate stale image callbacks. Responses to
`/api/status` and `/api/camera/progress` are ordered by browser-local
request start, so delayed older camera state cannot reset a newer
preview. **Keep the regression tests** for these correctness fixes.
No WebSockets; the Pi camera/capture and mount safety code are separate.

## Network and preview handoff — 2026-10-31

**Solved in practice:** The old n100/Pi wireless arrangement produced
intermittent 0.5–1 s browser preview pauses; Pi-local camera acquisition,
JPEG processing and HTTP responded normally in sampled diagnostics.
Temporary direct Ethernet made the preview smooth. Replacing the
n100 with an **HP EliteDesk 800 G5 Mini** and using **external
BrosTrend Wi-Fi adapters on both ends** now makes the preview
**visually indistinguishable from direct Ethernet** according to the
operator. This is a field-observed result, not a formal latency
benchmark. The experiment did not isolate whether the old PC's
Wi-Fi, its antenna, the Pi radio, or the access point caused the
specific delays. No preview performance work is planned.

**Keep Station Mode:** AstroPi connects to the existing home
Wi-Fi; there is no AP/hotspot mode or offline browser-clock-sync
implementation. These were discussed as future possibilities
and explicitly deferred. AM3N Connect still requires verified
Pi NTP synchronization.

**Pi radio:** BrosTrend AC5L USB RTL8821CU (`0bda:c811`),
in-kernel `rtw88_8821cu`, with `Bazingas-Minions-USB`
autoconnect enabled, priority **50**, route metric **100**, and
MAC binding `74:19:f8:17:b1:f5` rather than a fixed `wlan`
name. Pi onboard radio previously used `Bazingas-Minions`
metric **600**. The operator requested `dtoverlay=disable-wifi`
in `/boot/firmware/config.txt`; no post-overlay `iw dev`
output has been provided. Only one Wi-Fi radio should appear
if the overlay took effect; a USB-only adapter can become
`wlan0`. Recovery commands are in SETUP.md.

**No temporary debugging code:** Timing probes, a
`/api/camera/diagnostics` endpoint and per-frame diagnostic
counters were deleted in commit `57e0e4f`. This cleanup removes
the stale camera-settings `queue.Full` HTTP handler (settings
are coalesced, not enqueued) and unused CSS selectors.
The **normal FPS/preview-processing/sensor-signal readouts,
alternating JPEG loader, stale-response ordering and tests
are intentional working features**, not remaining experiments.
Do not regress them just because network transport is now smooth.

Full previous investigations are available in Git history,
not needed for a fresh development instance. Pi-owned RAW/FITS
recording is isolated from browser timing; mount Stop's
600 ms watchdog and physical Cancel/power backup are still
required even with a good wireless connection.

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
   to sync UTC offset/date/time **and initialize the permanent site**
   using fixed **+45.2933° N, −75.8571° east-positive** (approved by the
   operator). AM3N setters round to arcminutes **:St+45*18# /
   :Sg075*51#**, followed by :Gt/:Gg and UTC readback verification.
   The site/clock remain marked unverified if an ACK/readback fails;
   manual jogging is unaffected and GoTo is blocked. The same routine
   is accessible on the idle mount using **Sync Time / Site**; separate
   **Refresh Clock / Site** remains read-only. The atlas still deliberately
   skips NTP checking, independently of mount control. The Pi has no RTC. Reported RA/Dec
   and mount Home do not establish optical sky alignment.
   Never auto-Home, GoTo, slew or track when opening AstroPi.

## Offline VirtualSky and Find stage 1 — now implemented

The first atlas is **locally packaged**; it does not add Flask `/atlas`
or any mount command API. All sky rendering is confined to
`astropi/static/atlas.js`, a replaceable adapter loaded alongside
`app.js`. The Find panel's placeholder was replaced by an offline sky
chart, Messier search, horizon/detail controls and toggles. Vendor files
are pinned to upstream tree `271c801d6504d1c478bc0c64dce4938399749c69`
(virtualsky 0.7.7), with provenance/permission notes beside the files.
The local library loads `stars.json`, `lines_latin.json`, `lang/en.json`
and the local planet ephemeris plugin. All 110 Messier targets are
supplied by local `messier.json`; each pointer explicitly sets
`html: ""`. This both suppresses VirtualSky's default remote Wikisky
links/images **and disables the floating information box that the
bundled VirtualSky opens on mouse movement**. The latter covered the
clickable M-label/marker during field testing. Show selected object
details in AstroPi's persistent readout instead; do not restore
nonempty pointer HTML. Do not enable remote object name resolution.

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
toggles. **Selection alone is informational and sends no mount command.**
The separate GoTo button requires confirmation; no automatic tracking,
alignment, Home or Park operation is initiated by selection. On Find reveal call
`resize()`, keeping the chart inside the persistent DOM. Do not clone
camera preview/settings nodes. Global Stop and jog-on-tab-departure
Stop remain untouched.

**Messier click hit testing (2026-10-31):** VirtualSky's `whichPointer()`
only detects clicks within five pixels of the marker centre, not its
visible M-label. `clickedMessier()` first accepts a native pointer
match, then reprojects the plotted pointers to the current view and
checks a 12px marker radius or the corresponding on-canvas text bounds.
Only labelled catalogue Messier pointers may be selected; blank sky,
ordinary stars and off-horizon markers cannot accidentally select a
target. Search and mouse clicks both invoke `selectObject()`; neither
calls the mount. Keep regression tests for missed pointer matches,
left/right polar labels and empty/off-horizon clicks.

**Find stage 1 (2026-10-31):** `astropi/static/coordinates.js`
calculates selected Messier coordinates from catalogue J2000 RA/Dec
using IAU 1976 mean precession to date, mean sidereal time,
and the permanent fixed site (lat +45.2933, east-positive lon -75.8571).
The local altitude, true-north azimuth and above/below **geometric**
horizon readout updates from the same Pi UTC clock as VirtualSky.
It is approximate, **not** proof that a target clears trees,
mount travel limits or that an unaligned telescope is pointed at it;
no atmospheric refraction, proper motion or topocentric effects are
included. The separate GoTo button was subsequently enabled for a ready
mount. See Stage 2 below for the native command implementation.

**Find stage 2 — native catalogue GoTo (2026-10-31):**
`POST /api/mount/goto` accepts only an operator-held `{"target":"M31"}`
for an exact M1–M110 in the Pi's trusted local catalogue. The backend
independently reads that catalogue and precesses J2000 RA/Dec to the mean
equator/equinox of date (IAU 1976, matching `coordinates.js`).
The sole serial worker sends validated `:SrHH:MM:SS#`,
`:Sd±DD*MM:SS#` setters (each expects 1), then `:MS#` (expects 0);
reply may include `#`. This follows the INDIGO AM driver protocol,
not yet tested on this actual AM3N firmware. **Never permit raw serial
command or browser-provided RA/Dec.** Preconditions: connected, idle,
no conflicting job, **both** `time_sync_phase=verified` and
`site_sync_phase=verified` from Connect or manual Sync.
One confirmation click starts motion. Status includes goto_phase,
goto_target, goto_error and reported angular difference; a pair of
N/not-slewing telemetry samples within 0.35° marks reported completion,
which is **not optical verification**. After five minutes without
completion, request Stop and report failure. The global viewer-accessible
Stop cancels queued/sending/slewing GoTo, disarming it; normal serial
stop/settling verification remains in place. GoTo is autonomous and is
not a manual-jog heartbeat, so the 600 ms deadman still applies only to
manually held jog directions. Operator release requests Stop if an
active GoTo is underway. No mount limits or local obstruction map was
added; the operator says there are no obstructions at the indoor test
location. The mount can still reach mechanically unexpected positions.
**2026-10-31 initial real-Pi GoTo failure:** user reports pressing the
confirmed GoTo immediately produces "Stop requested" followed by
"Mount stable" with no physical movement. This means `_service_goto`
likely handled a command error and queued Stop; there is no evidence
that the mount accepted :MS or began moving. `/api/mount/status`
exposes `goto_phase`, `goto_error`, `last_stop_reason`,
`motion_phase` and `time_sync_phase`. Inspect those **before changing
the protocol**. The proven ZWO/INDIGO native sequence remains
:Sr (expect 1), :Sd (expect 1), :MS (expect 0); exact AM3N
firmware replies need field verification. The browser now keeps the
precise GoTo error in the global warning and mount motion display even
after Stop stabilizes. Do not mistake "Axes stable" for "GoTo
completed", and do not automatically retry rejected commands.
**Real AM3N diagnosis:** `/api/mount/status` returned
`goto_error="AM3N rejected :MS (reply b'e7#')"` on M39, mount
firmware 1.8.8. The INDIGO ZWO driver maps **e7 = time and location
are not set**. The old Connect set only UTC; it never sent site
setters despite a readable stored location. The new auto time/site
sync sends both and verifies each, and manual Sync is provided. **Next
field test:** confirm new site/clock readback, repeat GoTo, verify
physical motor movement and global Stop. No hardware confirmation yet.
Outdoor star alignment is later.


**Tracking stage (2026-10-31):** native operator-only
`POST /api/mount/tracking` with strict boolean `{"enabled":true|false}`
queues only `:Te#` (ON) or `:Td#` (OFF) through the one serial owner.
Status `:GAT#` independently reports `0`/OFF or `1`/ON; malformed
responses become UNKNOWN, never false OFF. A setter ACK must be followed
by matching :GAT readback, otherwise the command reports an error.
Status includes `tracking`, `tracking_phase`, `tracking_target`,
`tracking_error`, `tracking_status_error`. ON requires verified Pi
clock/site; OFF is allowed without. Both require connected/idle,
nonconflicting mount. No implicit tracking toggle on GoTo, Connect,
startup or target selection. Site/time re-sync requires tracking OFF.
Global STOP retains the proven :Q# slew/jog semantics; use explicit
Tracking OFF to stop tracking. CI simulated; operator subsequently **field-tested ON/OFF and readback**
on firmware 1.8.8. Mount initially reported Tracking ON after Connect.
Any automatic tracking transition specifically caused by GoTo remains
unverified; app leaves Connect and GoTo tracking unchanged.

**Real-hardware milestone (2026-10-31):** M40 GoTo produced correct
Alt/Az and reported completion; emergency STOP interrupted M45 GoTo.
Those tests establish motor response and reported-position behaviour,
**not optical celestial alignment**.

**North/Level physical setup checkpoint (2026-10-31):**
`POST /api/mount/north-level` accepts only an operator-held strict JSON
boolean `{"confirmed":true|false}`. Confirmation is accepted only if
serial Connect is active, mount `motion_phase=idle`, tracking is
**positively reported OFF**, and no queued/pending serial operation
exists. Absence of the AM3N `H` Home flag is *unknown*, so native Home
is confirmed by the operator physically, not inferred by the Pi.
Confirmation updates status fields `north_level_confirmed` and
`north_level_confirmed_utc`, with no serial command or mount coordinate
transformation. Clear invalidates the checkpoint (e.g. tripod moved);
disconnect/reconnect or process restart invalidates it automatically.
Normal jog and GoTo deliberately **do not clear** the initial physical
reference. The operator procedure is: level tripod/base, return AM3N to
native Home via hand controller, physically orient mount/tripod to true
north, turn tracking OFF and press **Confirm North / Level** in the
Mount Controls drawer. No app Home command, motor jog, electronic mount
sync, sky model or two-star alignment occurs. GoTo remains available
without this optional physical checklist until actual star-alignment
code is implemented. Do not label confirmation 'celestially aligned'.
Tests cover lease, strict payload, idle/tracking guards, no serial
commands and session reset. Real-Pi visual verification is pending.

**Verification:** `tests/test_atlas.py` checks local assets, all 110
catalogue entries and motion-free adapter. `tests/test_atlas.cjs`
checks Pi UTC, search/clicks, projections and offline loading;
`tests/test_ui.cjs` covers retained tab safety and atlas DOM. CI success does not imply
a real-Pi rendering test: verify offline loading and chart dragging,
M1/M31/M42/M110, no remote requests, UTC, responsive layout, mount
Stop, and unbroken capture/lease continuity on the actual Pi.

**Deferred:** OpenNGC NGC/IC catalogue and filter-independent search,
read-only mount marker, two-star alignment,
optical GoTo accuracy, focus zoom/HFR, plate solving, stacking,
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
