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
`/api/camera/frame.jpg`, `/api/capture/status`, `/api/mount/status`.

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

## Wireless preview findings and current field setup

**Diagnosis (2026-10-29):** Pi SDK/JPEG completion intervals stayed
~109/133 ms maximum in a sample taken through the freezes, while
browser and independent Mint-to-Pi Wi-Fi HTTP had occasional ~0.5–1 s
delays. Pi-local HTTP was ~2–10 ms. Disabling Wi-Fi power saving and
using a numeric IP did not eliminate pauses. **Temporary direct
Ethernet made the preview silky smooth** with unchanged application
code: wireless delivery is the main identified contributor, though
the exact adapter/AP fault remains unknown. History of the
investigation is preserved before cleanup commit `57e0e4f`.
There is **no plan to install permanent Ethernet or re-engineer the
preview for this minor focusing annoyance**.

**New Pi Wi-Fi (2026-10-29):** BrosTrend AC5L USB `0bda:c811`,
`rtw88_8821cu` on Pi kernel `6.18.39+rpt-rpi-v8`, firmware
`24.11.0`; `wlan1` while onboard was present. Its saved
NetworkManager profile `Bazingas-Minions-USB` is autoconnect=yes,
MAC-bound to `74:19:f8:17:b1:f5` (not interface-name bound),
priority=50 and IPv4/IPv6 metric=100. Internal profile
`Bazingas-Minions` had priority=0, metric=600. USB adapter
tested across multiple reboots, associated at 5 GHz with signal
as strong as −44 dBm, and live preview worked with fewer—but
persistent—brief pauses. Client Mint's second AC5L was **ordered,
not yet installed or tested**.

**Onboard-radio change:** The operator requested the Raspberry Pi
boot overlay `dtoverlay=disable-wifi` to reduce power/heat. We
provided commands to add it to `/boot/firmware/config.txt` and
to restore the radio via Ethernet if USB networking fails. **No
post-overlay reboot output was received**; do not claim verified
absence of the onboard interface. After disabling it, the USB
adapter may be renamed from `wlan1` to `wlan0`; use the
MAC-bound NetworkManager profile, `nmcli`, and `iw dev`,
not a hardcoded interface name. See SETUP.md.

**Architecture:** Pi-owned RAW/FITS science acquisitions, sequence
scheduling and local USB storage do not wait for browser JPEG
loads. This does not imply the exact wireless hiccups were tested
during a saved science run. Wi-Fi may delay manual mount control;
retain server-side 600 ms deadman and physical Cancel/power fallback.

**Clean state:** Temporary browser probe, server camera-timing API
and per-frame diagnostic event counters were already removed in
`57e0e4f`. Live preview processing/FPS fields, alternating JPEG
loader, stale-response guard and regression tests are intentional
features. Do not resurrect old troubleshooting code without evidence.

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
