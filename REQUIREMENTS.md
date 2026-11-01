# AstroPi — selected requirements

**These are scope decisions, not a list of completed features.** Read
[README.md](README.md) for what works, [HARDWARE.md](HARDWARE.md) for
field evidence and [DEVELOPMENT.md](DEVELOPMENT.md) for the next build.
IDs correspond to the original 70-item feature menu.

## Camera (SVBONY SV705C only)

| IDs | Selected scope | Current state |
| --- | --- | --- |
| **#1, #4, #5** | One SV705C, responsive preview, manual exposure/gain | **Implemented**, Pi-tested |
| **#6** | Supported ROI/resolution/binning | **1×1 and 2×2 binning implemented/field-tested**; arbitrary ROI deferred |
| **#8** | Display-only colour/debayer and white balance; preserve RAW | **Debayer On/Off implemented**; separate white-balance adjustment deferred |
| **#9** | Histogram and display stretching | **Auto/Fixed stretch + raw statistics implemented**; histogram deferred |
| **#10–12** | Peaking, star sharpness metric/graph (FWHM/HFD/HFR) and simple zoom | **Deferred** until after Find/VirtualSky |

Exposure presets run 1 ms–30 s. Gain presets are
**0/50/100/260/350/450/550/650**, deliberately selected by the
operator without a camera-capability query; the operator has observed
the expected image response. Sensor HCG threshold and max gain have
not been independently calibrated.

## Mount (ZWO AM3N, Alt/Az only)

| IDs | Selected scope | Current state |
| --- | --- | --- |
| **#14–17** | Serial Connect, reported coordinates, hold N/S/E/W, five speeds, Stop and deadman | **Implemented**, with field checks |
| **#18** | GoTo **only after choosing an atlas target and explicitly pressing GoTo**, never manual RA/Dec entry | Select-first UI and disabled GoTo placeholder implemented; motion deferred |
| **#19** | Tracking control/status; AM3N firmware handles Alt/Az tracking | Deferred (some status flags are read-only) |
| **#20** | Native Home and separate Park, carefully verified | Deferred; earlier standalone Home probe is **not** a UI feature |
| **#21–22, #26** | Initial north/level, manual two-star and optional extra-star alignment | Deferred |

Five existing manual speed presets: **8× / 20× / 60× / 720× /
1440×**. No arbitrary fixed jogging-time cutoff. Keep a global
viewer-accessible Stop, release/blur/tab-switch Stop, 600 ms missing-
heartbeat watchdog, serial-owner command whitelists and stable-axis
verification. Software Stop cannot guarantee physical motor stopping.

**Permanent site:** user confirms the AM3N-stored latitude
**+45.2933° N** and east-positive longitude **−75.8571°** are the
real permanent observing location (AM3N serial encoding is
**west-positive**). App reads these values; **do not overwrite them**.
On explicit mount Connect, only if Pi NTP is synchronized, set and
verify AM3N UTC date/time and offset zero; fail visibly on bad ACK or
readback. **This existing mount-control safety condition remains unchanged
and is independent of the atlas.** Pi has **no RTC**. Neither mount RA/Dec nor native Home
proves optical sky alignment; verify site and alignment before
introducing GoTo.

## Offline atlas — Find tab (v0.1 and stage 1 implemented, Pi verification pending)

**#28–30, #32** are selected long-term requirements. VirtualSky v0.1,
110-object Messier search and live selected-target geometric Alt/Az/visibility
are now in code; full OpenNGC/NGC/IC remains deferred.
Real-Pi atlas verification is pending.

**VirtualSky v0.1 (implemented in Git):**
- Embed locally packaged VirtualSky and its own JS/JSON assets in the
  **existing Find tab** of the persistent browser application;
  schematic symbols only, **no photographic imagery**, online lookup,
  CDN or Internet requirement. Wrap chart integration in a replaceable
  adapter.
- Display local sky from the **permanent site**, using current **Pi UTC**
  already supplied by `/api/status` when Find opens and on subsequent
  status updates. Accept the Pi's time as-is: **no atlas NTP status field,
  time-accuracy check, or unsynchronized-clock warning** is required,
  now or as a planned follow-up. A mount-site mismatch may still be shown
  when the AM3N is connected; never overwrite the stored site.
- Horizon view and pan; centred detail view/zoom; stars/planets,
  horizon/cardinal directions, constellation lines/labels and RA/Dec grid.
- Bundle all **110 Messier objects** for basic `M1`–`M110` search,
  click/centre and **name/RA/Dec** details. Selection is informational;
  **no GoTo/mount motion** in v0.1. Stage 1 separately displays
  approximate altitude, true-north azimuth and above/below geometric
  horizon using J2000-to-date precession and Pi UTC. The separate GoTo
  button remains **disabled**. Local obstructions, mount limits and
  alignment are not inferred from these coordinates.

**Later:** full local **OpenNGC NGC/IC** catalogue (#28), full catalogue
search independent of plot filters (#30), and a carefully labelled
reported/estimated mount marker (#32). Alignment and GoTo are still
separate later milestones.

## Capture and safety

- **#38–40:** Original RAW16 science samples, correct FITS metadata,
  display-only JPEG/PNG quicklooks, and counted Pi-owned captures
  (**implemented**).
- **#48:** Explicit per-format choices, USB-only storage with verified
  mount/UUID and **no microSD fallback** (**implemented**).
- No manual bit-depth switch (#7): 12 valid sensor bits in 16-bit
  containers; 8-bit preview may be used without altering RAW/FITS.
- Sequences continue through browser/tab closure but not server/Pi
  restart; cancellation stops at a safe write boundary. No unbounded
  capture queue.

## UI and operation

- **#53–54:** Responsive dark UI, not all-red (**implemented**).
- **#56–57:** Pi-owned sequences and honest camera/mount/USB/host status
  (**implemented**).
- **#59:** Multiple LAN viewers, **one 15 s lease-based operator**;
  only the owner changes settings/moves the mount, but any viewer may
  request Stop (**implemented**). Trusted LAN only, **no user accounts**;
  never expose Flask's development server publicly.
- **Focus / Find / Fotograph** are **implemented as three persistent
  tabs**, not separate pages. The same preview/settings nodes move
  between Focus and Fotograph. Find contains the offline atlas only.
  A **single shared mount control card** slides in from the right
  as an **overlay drawer**, available from all three tabs, and stays
  open across tab changes; no pin mode yet. Closing it or switching
  tabs while jogging sends Stop, but idle transitions do not.
  A closed drawer is inert and cannot begin a jog. Global viewer-
  accessible Stop stays above the overlay and visible in all tabs;
  ownership and Pi recording survive tab changes.

## Field connectivity (operator decision, 2026-10-31)

- **Station Mode only for now:** Pi connects to the
  existing Wi-Fi; no AP/hotspot switching or browser-based
  offline time sync is required. Mount Connect retains
  its Pi NTP verification.
- **Wi-Fi hardware:** Use the Pi's BrosTrend AC5L USB
  adapter, with a second external BrosTrend on the
  HP EliteDesk 800 G5 Mini client. Operator reports
  preview now as smooth as direct Ethernet; no further
  stutter remediation is planned. Avoid a permanent
  field Ethernet tether.
- **Pi internal Wi-Fi:** Operator requested disabling
  its radio at boot for modest power/heat savings;
  confirmation after reboot is pending (SETUP.md).
- **Preview isolation:** Keep Pi-owned RAW/FITS
  acquisition/recording separate from browser JPEG
  transport. Retain the frame loader and stale-response
  fixes, and do not add back temporary timing probes.

## Explicit exclusions

SV705C only; no alternative cameras, cooling or camera switching.
Deep-sky Alt/Az work, **not** planetary video. No automatic Home/GoTo/
tracking on startup. No plate solving/closed-loop centring (#23–25);
initial corrections are manual. No live stacking, registration,
derotation or stack processing (#44–47); process saved science data
later on a desktop. Do not silently add unselected original menu IDs.
