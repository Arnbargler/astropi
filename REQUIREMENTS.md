# AstroPi requirements and scope

**Selected features, not all implemented.** IDs deliberately match the
original 70-item feature menu. For **current implementation status**, read
[README.md](README.md); for verified commands use [HARDWARE.md](HARDWARE.md).

## Camera

- **#1** SV705C via Linux SVBONY SDK; one camera only.
- **#4** Responsive browser preview with modest network/CPU overhead.
- **#5** Manual exposure and gain.
- **#6** Supported ROI/resolution/binning choices (not yet implemented;
  only full-frame 1× acquisition verified).
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
verification. This is implemented and Pi-verified. Stored observing latitude
**+45.2933°** and east-positive longitude **−75.8571°** are presently read,
not changed automatically. AM3N protocol longitude is **west-positive**.
Validate stored site and alignment before sky GoTo. Future field operation
without NTP may need manual entry, RTC or GPS; the Pi has no RTC.

## Offline atlas (future)

- **#28** Local OpenNGC (NGC/IC) plus Messier catalogue.
- **#29** Local VirtualSky with schematic DSO symbols (not photographs);
  zoom/pan/selection, behind a replaceable application adapter.
- **#30** Search full local catalogue independently of plotted-object filters.
- **#32** Reported/estimated mount marker on chart.
- Browser catalogue/navigation must work without Internet.

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

## Exclusions and deferred decisions

- SV705C only; no SC571CC, ToupTek, cooling or camera switching.
- Deep-sky, Alt/Az only; no planetary video workflow.
- **No plate solving or automatic closed-loop centring** (#23–25 excluded).
  Alignment/pointing correction will initially be manual.
- **No live stacking, registration, automatic derotation or stack stretch**
  (#44–47 excluded); stack individual frames on a desktop afterward.
- No features from the original menu outside the selected IDs without a new
  user decision. No automatic Home/GoTo/track command on service startup.
