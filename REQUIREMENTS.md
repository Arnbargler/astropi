# AstroPi requirements and scope

**Selected features, not all implemented.** IDs deliberately match the
original 70-item feature menu. For **current implementation status**, read
[README.md](README.md); for verified commands use [HARDWARE.md](HARDWARE.md).

## Camera

- **#1** SV705C via Linux SVBONY SDK; one camera only.
- **#4** Responsive browser preview with modest network/CPU overhead.
- **#5** Manual exposure and gain.
- **#6** Supported ROI/resolution/binning choices. **1×1 and 2×2 hardware
  binning** are implemented and physically verified on the SV705C; the operator
  also confirmed correct 2×2 preview colours. Arbitrary ROI remains future.
- **#8** Display debayer/colour and white balance without changing sensor RAW.
- **#9** Histogram and display stretching.
- **#10** Focus peaking overlay.
- **#11** FWHM/HFD or comparable star sharpness metric and focus graph.
- **#12** Simple focus zoom choices (no complicated arbitrary region UI).

## Mount — ZWO AM3N, Alt/Az only

- **#14** Serial connection, live reported coordinates and status.
- **#15** Hold-to-move N/S/E/W controls.
- **#16** Selectable slew speed (original choice called for a slider; current
  interface uses **five presets**: 8×, 20×, 60×, 720×, 1440×).
- **#17** Prominent Stop, deadman on button release/browser loss, no conflicting
  direction commands; verify stable axes rather than assuming a sent Stop means
  motion ceased. **No arbitrary 3s jog cutoff** in the current design.
- **#18** GoTo **from atlas target selection only**, not manual RA/Dec entry.
- **#19** Tracking control/status; firmware performs continuous Alt/Az tracking.
- **#20** Native Home and separate Park, after controlled verification. Home
  does not imply astronomical alignment.
- **#21** Approximate north/level initial alignment at known Home.
- **#22** Manual two-star alignment.
- **#26** Optional additional manually centred alignment stars.

**Time and site:** On each explicit serial Connect, use the Pi's NTP-confirmed
UTC to set AM3N UTC offset zero, date and time; require replies and readback
verification. This is implemented and Pi-verified. The operator confirms
the site's stored latitude **+45.2933° N** and longitude **−75.8571°
east-positive** are the **permanent actual observing location**, not a
temporary test position. AM3N serial longitude is **west-positive**
(+75.8571° for this site). Read/compare mount site; **do not overwrite it**.
The offline atlas should use these coordinates even when the mount is
disconnected, and label any site mismatch or unavailable time sync.
Validate site and alignment before future sky GoTo. The Pi has no RTC.

## Find tab / offline sky atlas (agreed, not implemented)

- **#28** Local OpenNGC (NGC/IC) plus Messier catalogue; full NGC/IC
  integration is a **later** milestone, not a dependency for v0.1.
- **#29** Embed **VirtualSky**, with local JS/JSON assets, schematic DSO
  symbols (no astronomical photos), pan/zoom/selection and a replaceable
  adapter; no CDN, online lookup, or Internet dependency.
- **#30** Full local catalogue search independent of plotted-object filters
  once OpenNGC is added. **v0.1** starts with all 110 Messier objects,
  simple M-number search, centred selection, and name/RA/Dec details.
- **#32** Reported/estimated mount marker is deferred until its alignment
  limitations are clearly represented; it is **not** a v0.1 feature.

**VirtualSky v0.1** uses the permanent mount site and Pi UTC time, with
explicit NTP/synchronization status and an honest warning when time or site
cannot be trusted. Chart controls: mouse pan/zoom, constellation lines and
labels, horizon and cardinal directions, optional coordinate grids, and
stars/planets/Messier markers. It is a **pointing aid**, not a gallery;
never download photographic survey tiles or silently use a remote resolver.
Clicking/searching a target is informational only: **no movement/GoTo** in v0.1.

## Capture

- **#38** Preserve full-quality raw exposures and FITS with useful metadata.
- **#39** JPEG/PNG exports and preview-only processing.
- **#40** Counted exposure sequences run on the Pi, independently of browser.
- **#48** Selectable per-format saving of individual exposures; never silently
  write to OS microSD if the specified USB data filesystem is absent or full.

No manual bit-depth selector (#7). Full sensor science uses 12-bit values
in 16-bit containers; efficient previews may be 8-bit. FITS and RAW retain
the original mosaic sample values for later desktop processing.

## Interface and operation

- **#53** Responsive desktop/tablet/phone browser controls.
- **#54** Subdued dark theme, not an all-red display.
- **#56** Pi owns exposures/sequences through browser closure.
- **#57** Camera/mount/USB/host status, useful errors and ongoing progress.
- **#59** Many LAN viewers, **one operator lease**. Backend enforces ownership
  for settings and motion. Emergency Stop may be requested by a viewer.
  No passwords/accounts for the trusted LAN; don't expose the Flask development
  server to the Internet.

**Agreed UI redesign (not yet coded):** a single persistent AstroPi browser
application with three tabs, **Focus / Find / Fotograph**. Avoid a separate
`/atlas` page or reload-based navigation. The Raspberry Pi continues to
own the *one* camera SDK worker, mount serial worker, capture manager and
operator lease shared across all tabs.

- **Focus:** live preview and camera settings needed to focus; later click-
  centred zoom/peaking/HFR. These aids are deferred until after the atlas.
- **Find:** dominant offline VirtualSky chart, object selection and AM3N
  manual mount controls/status; future alignment, mount marker and GoTo.
- **Fotograph:** existing full preview, exposure/gain, binning, display
  settings, FITS/RAW16/JPG/PNG and counted captures/USB/host status.
- Shared visible navigation/status and **emergency STOP MOUNT on every tab**,
  including for viewers. Maintain the operator heartbeat across tab changes.
  Switching tabs must not stop the camera, cancel Pi-owned recording or
  release operator ownership; an active jog must Stop when leaving Find.
  No new movement commands from merely viewing/selecting a chart.

First deliver the tab shell preserving existing controls; then integrate the
offline chart in Find. Keep mount control and capture safety regressions.

## Exclusions and deferred decisions

- SV705C only; no SC571CC, ToupTek, cooling or camera switching.
- Deep-sky, Alt/Az only; no planetary video workflow.
- **No plate solving or automatic closed-loop centring** (#23–25 excluded).
  Alignment/pointing correction will initially be manual.
- **No live stacking, registration, automatic derotation or stack stretch**
  (#44–47 excluded); stack individual frames on a desktop afterward.
- No features from the original menu outside the selected IDs without a new
  user decision. No automatic Home/GoTo/track command on service startup.
