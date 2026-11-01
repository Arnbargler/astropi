# AstroPi — new-chat handoff

**Updated: 2026-10-31 · branch: `main` · repository:
[Arnbargler/astropi](https://github.com/Arnbargler/astropi)**

**Start here.** This is the compact engineering handoff. Do not infer
hardware success from GitHub CI. Read `README.md` for the functional
overview, `REQUIREMENTS.md` for agreed scope, `HARDWARE.md` for actual
hardware/protocol evidence, `DEVELOPMENT.md` for implementation
invariants and `SETUP.md` for Pi procedures. Git history holds prior
experiments, **not** instructions to restore old features.

## Equipment and app

- Pi 4B **4 GB**, Debian 13 Trixie ARM64; `arn@astropi`.
  Flask app runs in foreground on **port 8080**; no systemd startup yet.
- Camera: **SVBONY SV705C**, USB3, 3856×2180 RAW16 (12 valid bits);
  SDK at `~/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so`.
  Recordings **must** use verified `/media/astropi-data` USB storage.
- Mount: **ZWO AM3N**, firmware **1.8.8**, Alt/Az only, serial USB
  `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`,
  9600 8N1. No direct client serial commands.
- Site (user-approved permanent): **45.2933° N, 75.8571° W**;
  AM3N rounds to whole arcminutes when setting site. Pi UTC from NTP
  is synchronized to mount **on explicit Connect**, with verified site
  readback; atlas deliberately doesn't require a separate NTP check.
- Front end: **Focus / Find / Fotograph** persistent tabs; one shared
  preview/settings instance. **Mount Controls** right-side drawer is
  available from every tab; global viewer-accessible **STOP MOUNT**
  remains outside it. Single operator lease controls movement.
- Wi-Fi: Pi BrosTrend AC5L USB / HP EliteDesk 800 G5 Mini client
  using external adapters, Station Mode; preview looks as smooth as
  Ethernet to user. Preserve existing two-buffer JPEG/stale-status fixes.

## Real-hardware verification

- Camera live preview, 1×1 and 2×2 colour, gain/exposure, capture,
  FITS/RAW and much of the three-tab UI: field-tested. Some 2×2 FITS
  metadata remains explicitly marked unverified.
- VirtualSky: locally packaged, Messier 110, schematic atlas,
  selection/popup behaviour field-tested. Selected Alt/Az is **computed**,
  not physical pointing proof.
- Native **GoTo M40**: physically moved correctly and completed at
  mount-reported coordinates. **Global STOP during M45 GoTo** worked.
  Neither test validates actual optical sky alignment.
- Tracking `:GAT#`, `:Te#` ON and `:Td#` OFF: user repeatedly
  tested and saw correct OFF/ON and verified UI results. Tracking
  reported **ON immediately after Connect**, even though AstroPi never
  explicitly enables it on Connect.
- North/Level physical setup confirmation: user reported it functions
  correctly. It is a UTC-stamped **operator acknowledgment**, not mount
  coordinate alignment. Resets on disconnect/process restart. Jog/GoTo
  do not clear the checkpoint.
- **Az Home browser button: implemented and CI-tested, not yet tested
  on the real mount from AstroPi.** It uses native `:hC#` (both axes),
  requires Alt/Az and Tracking OFF, and watches `:GU#` for H + N across
  two polls. Native Home itself was previously proven in a standalone
  serial probe. Software STOP must remain usable during Homing.

## Most useful next hardware check

1. Stop current Flask, pull `main`, restart, hard-refresh.
2. With clear mechanical travel and physical Cancel/power available,
   take control, Connect, **Tracking OFF**, jog a little away from
   native Home, press **Az Home**. Check actual movement and reported
   completion. Test STOP during a second Home motion if safe.
3. Report the exact `home_phase`, `home_error`, `at_home`,
   `motion_phase` from `/api/mount/status` if behaviour differs.
   During hand-controller Home the firmware temporarily returned
   tracking query error `e5` but reached Home successfully. The app
   shows tracking **UNKNOWN** for this reply; don't equate it with
   Home failure.
4. Then plan **two-star alignment** in Find. Don't claim optical
   alignment based on native Home, operator North/Level confirmation,
   or the mount's reported RA/Dec alone.

## Boundaries and unfinished work

- **Physical setup:** level base/tripod; native Home; physically turn
  entire assembly to **true north**; Tracking OFF; operator presses
  Confirm North / Level. This action sends **no motor command**.
- **Az Home:** separate, explicit motor movement to native Home;
  **not** setting Home, Park, rotating the tripod or two-star alignment.
- **GoTo:** user selects M1–M110 in Find and explicitly confirms;
  Pi worker independently precesses the local catalogue coordinates.
  Requires verified UTC **and** site. Current completion is
  **mount-reported**. GoTo does not explicitly set tracking; unknown
  whether the AM3N toggles it itself during a slew.
- No automatic Home/slew/GoTo/tracking on page load or Connect.
  No user-provided raw serial or arbitrary coordinate commands.
  Pi owns USB camera, captures and one exclusive mount serial worker.
  Manual jog has 600 ms heartbeat deadman; global STOP is not a
  substitute for physical Cancel/power if hardware/serial fails.
- Not yet implemented: two-star alignment, plate solving, native Park,
  full NGC/IC catalogue, focus ROI/zoom, stacking, service auto-start.
  Avoid restoring earlier focus peaking/HFR UI, fixed jog time limits,
  atlas NTP warnings or experimental network timing probes without
  a fresh request.
- VirtualSky bundled assets carry specific upstream provenance terms;
  see `astropi/static/vendor/virtualsky/PROVENANCE.md` before
  redistributing.

## Working on the code

Use the connected GitHub repository; inspect `main` and current docs
before editing. Python tests simulate serial/camera; Node tests emulate
browser behaviour. **CI success is necessary, not a hardware test.**
Retain the existing motion/STOP invariants and the operator's
ability to use mount controls from every tab.

```bash
# On the Pi, stop the prior foreground server first
cd ~/astropi
git pull --ff-only
source .venv/bin/activate
python -m pytest -q
python run.py --host 0.0.0.0 --port 8080

# On a machine with Node 22+, optional UI/atlas tests
node --test tests/test_ui.cjs tests/test_atlas.cjs
```

**Best immediate next chat prompt:** "Read `HANDOFF.md` in
`Arnbargler/astropi`; review current main. Let's test Az Home on the
real AM3N and then design two-star alignment." 
