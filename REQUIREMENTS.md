# AstroPi Requirements

This file is the **selected feature set** for AstroPi. Numbers below are retained from the original 70-item à-la-carte menu so we can refer to them unambiguously. Listed items are **requirements, not implemented features**.

## A. Camera operation

- **#1 — SV705C camera support:** Use the SVBONY Linux SDK to operate the SV705C.
- **#4 — Live camera preview:** Browser-accessible preview, optimized for responsiveness and low network bandwidth.
- **#5 — Exposure and gain:** Manual browser controls for supported exposure times and gain.
- **#6 — Resolution, ROI and binning:** Expose supported resolution, region-of-interest and binning controls.
- **#8 — Colour processing:** Debayering, white balance and display colour adjustments without altering raw source data.
- **#9 — Histogram and image stretching:** Basic preview brightness/stretch controls and histogram.
- **#10 — Focus peaking:** Visual focus-assist overlay.
- **#11 — Numerical focus measurement:** Star sharpness measurements (e.g. FWHM/HFD), with a focus-quality graph.
- **#12 — Focus zoom:** Simple selectable zoom levels for focusing. Avoid an unnecessarily complicated region-selection system.

## B. ZWO AM3 mount control and alignment

- **#14 — AM3 connection and status:** Serial connection, current reported coordinates and mount status, for **Alt/Az operation only**.
- **#15 — Manual movement:** Browser directional movement controls.
- **#16 — Slew speed:** **Slider** to select manual movement speed.
- **#17 — Stop and movement safety:** Prominent stop control, release/disconnect timeouts for manual movement, and prevent conflicting commands.
- **#18 — GoTo via the atlas only:** Select a target on the sky chart and send its coordinates internally to the mount. **No user-facing manual RA/Dec entry.**
- **#19 — Tracking control:** Turn mount tracking on/off and show its reported status; mount firmware handles the continuous two-axis tracking.
- **#20 — Home and Park:** Safe home/park actions, validated against the AM3's Alt/Az behaviour and firmware.
- **#21 — Quick North/Level alignment:** Start with a roughly levelled, north-oriented telescope at a known home position.
- **#22 — Manual two-star alignment:** Select and center two reference stars to improve GoTo pointing.
- **#26 — Multi-point alignment refinement:** Optionally add further manually centered reference stars to refine the pointing model. Do not require plate solving.

**Mount time and site initialization (implementation requirement, not yet built):** The Raspberry Pi's NTP-synchronized system UTC clock is the source of time. On each mount connection/reconnection (not only when the Pi boots), AstroPi must wait for a trustworthy Pi clock, load the configured observing site, set the AM3N's **UTC offset to 0**, date, time, longitude and latitude over its verified serial connection, and read back/verify the settings before enabling celestial GoTo or tracking-dependent sky features. The correct site, supplied by the owner, is **+45.2933° latitude, −75.8571° longitude** (east-positive astronomical convention); convert longitude to ZWO's **west-positive** convention only at the serial driver boundary. Prefer stable `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`; retry if the mount powers up after the Pi. The Pi's own NTP configuration is already active, but **automatic mount synchronization is not currently implemented**. Whether the AM3N retains location and time across a power cycle has not been tested; configure both on every connection regardless. Since the Pi has no RTC, a field boot with no Internet/NTP requires a separate trusted time source (e.g. browser-provided clock with explicit confirmation, an RTC or GPS) before GoTo; do not silently accept a stale clock. Startup should not block the camera UI indefinitely while awaiting NTP or the mount.

## C. Offline sky navigation

- **#28 — Offline DSO catalogue:** Use **OpenNGC** (approximately 14,000 NGC/IC objects) and a Messier catalogue, served locally.
- **#29 — Interactive sky chart:** Use **VirtualSky** with **traditional schematic DSO symbols, not photographs**; browser zoom/pan/selection.
- **#30 — Object search:** Search local objects by catalogue name/designation and select a target.
- **#32 — Mount-position indicator:** Show the telescope's reported/estimated position on the sky chart.

**Atlas integration note:** Keep VirtualSky behind an AstroPi adapter so we can replace it without rewriting mount control. Test full OpenNGC loading, filtering, labels, DSO symbols and click-to-GoTo performance before relying on it. The full catalogue must remain searchable even if display objects are filtered by zoom or field of view. Internet access must not be needed for the chart.

## D. Capture and image processing

- **#38 — Single-image capture:** Save full-quality SV705C raw sensor frames, preferably as FITS with useful metadata.
- **#39 — JPEG/PNG export:** Save or export processed/display images in browser-friendly formats.
- **#40 — Exposure sequences:** Run a specified number of exposures of a selected duration on the Pi.
- **#48 — Optional file saving:** Checkbox-controlled saving of individual high-quality raw exposures (including sequence frames) and image exports. When saving is enabled, preserve individual frames for later alignment, field-rotation correction and stacking in external astrophotography software. No live-stack files.

**Image-precision decision:** There is **no manual bit-depth selection** (#7 is not a user-interface feature). Use highest suitable SV705C sensor precision for recorded DSO data (12-bit sensor values in a 16-bit storage container), while serving efficient 8-bit compressed previews to browsers. Preview processing must not damage the original raw data.

## E. Browser and operation

- **#53 — Responsive browser interface:** Usable on a desktop, tablet or phone.
- **#54 — Subdued dark theme:** A tasteful low-brightness astronomy interface, **closer to N.I.N.A. than a bright SharpCap-style screen**; not an entirely red interface.
- **#56 — Background operation:** The Pi owns ongoing exposures and capture sequences; browser disconnect or reload must not stop them.
- **#57 — Status display:** Camera/mount connectivity, current operations, frame status, basic Pi health, and meaningful errors.
- **#59 — Multiple viewers / Take Control:** Multiple browser clients share one camera feed. Exactly one active operator may control camera and mount at a time. Provide **Take Control** and release/timeout handling. **No user accounts, passwords or access-control security for this trusted local setup.** The backend must still enforce operator ownership to prevent conflicting commands, and a disconnected operator's continuous manual slew must stop.

## Explicit scope boundaries

- **Camera:** SV705C only. Do not implement the SC571CC, ToupTek driver, camera switching or camera-cooling support.
- **Observing:** Deep-sky targets, **Alt/Az only**. No planetary high-speed/video feature set.
- **Not selected:** #23 plate solving, #24 automatic plate-solve alignment and #25 automatic GoTo centering. Pointing refinement will be **manual** via selected alignment stars. Do not silently add these features.
- **No live stacking:** #44–#47 are excluded. No live frame registration, Alt/Az field-rotation correction, live bad-frame rejection, or live-stack stretch; those tasks may be performed later using desktop astrophotography processing software.
- **All other menu features not listed above remain out of scope** unless explicitly selected later.
- **Status:** Design requirements recorded; software implementation and real hardware validation remain future work.
