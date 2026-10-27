# AstroPi development guide (read-only browser skeleton present)

**Status: read-only browser service verified on Pi (2026-10-27); first integrated SV705C preview failed in control initialization with SDK code 16. Exposure-before-gain fix is coded and awaiting Pi verification.** Read [REQUIREMENTS.md](REQUIREMENTS.md) for authoritative scope and [HARDWARE.md](HARDWARE.md) for **actually verified** devices and quirks. This file is a recommended route to implementation, **not a claim that the proposed hardware-control modules or system services already exist**. Keep implementation modular and modest; avoid one enormous `app.py`.

## First working milestone

Build a small **Pi-hosted Python backend** with a browser UI that can connect to the one SV705C, produce live colour previews, set exposure/gain, save individual full-resolution RAW/FITS captures to the UUID-verified USB data drive, and show clear errors. It must not require the N100 desktop to operate. The UI uses **Flask**; experimental camera preview is committed, but hardware camera integration still needs Pi testing. Full-quality capture, mount control and systemd integration remain unimplemented.

Do not build a general camera-agnostic driver system or implement unselected features. Run on trusted local Wi-Fi/LAN; Internet access must not be necessary for operation except optional NTP syncing.

## Suggested modules and ownership

| Module (illustrative names) | Responsibilities |
| --- | --- |
| `camera/sdk.py` | **Sole owner of SVBONY SDK handle**; enumerate/info/open before configuration; get frame; controls; safe stop/close; bounded timeout/reconnect. Avoid concurrent direct SDK calls from web requests. |
| `camera/preview.py` | RAW16 (probable 12-bit left-shift 4) → GRBG demosaic/bin → stretch, white balance, efficient 8-bit JPEG/PNG preview, histogram and focus metrics. Preserve original RAW. |
| `capture/session.py` | Single exposure and timed sequence orchestration independent of browser connection; one camera acquisition path; optional high-quality recording vs preview-only; meaningful status. |
| `storage.py` | Verify `/media/astropi-data` **has correct mounted UUID**, space and permissions *before every recording*. Crash-safe `.partial` → `fsync` → atomic rename. FITS metadata including timestamps, settings, site, resolution, Bayer. No SD-card fallback. |
| `mount/serial.py` | Own **one serialized AM3N USB serial connection** and command queue; use by-id alias, explicit timeouts and validated replies; never send conflicting movement commands. |
| `mount/safety.py` | Operator-controlled **Stop**, manual jog deadman on release/disconnect and bounded duration; request `:Q#` then verify `:GU#` and altitude/azimuth stable across polls; access to physical Cancel/power fallback. |
| `mount/pointing.py` | Home/Park/GoTo/tracking with state and limits, UTC/site sync on connect, Alt/Az coordination, user-driven alignment model. **These sky functions are unvalidated**. |
| `sky/catalog.py` / `sky/atlas.py` | Offline OpenNGC/Messier index and VirtualSky integration via replaceable adapter; sky-chart object selection → internal GoTo only. No manual RA/Dec entry UI. |
| `server/` and `web/` | Responsive subdued-dark interface; multiple read-only viewers; exactly **one operator lease** with Take Control, timeout, consistent state feed; no login system on trusted LAN. |

The split is conceptual; exact filenames and language for frontend are not yet decisions. Add unit tests for coordinate conversion, loss of operator lease, missing storage, session lifecycle and serial parsing. Keep Pi-specific hardware tests separate from pure code tests.

## Camera integration rules derived from working probes

1. Library exists on Pi: `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so`; SDK headers are under `.../include/`. Don't vendor SDK binaries in Git.
2. `SVBGetNumOfConnectedCameras()` → `SVBGetCameraInfo(info,index=0)` → **use `info.CameraID`** → `SVBOpenCamera(id)`. Verified camera info struct: three `char[32]` fields (`FriendlyName`, `CameraSN`, `PortType`), `unsigned int DeviceID`, `int CameraID`. `CameraID=1` in tests but is not a configuration constant.
3. Full RAW16: `SVBSetROIFormat(id,0,0,3856,2180,1)`, `SVBSetOutputImageType(id,4)`, buffer size `16,812,160` bytes; `SVBStartVideoCapture` and `SVBGetVideoData` return full frames, followed by `SVBStopVideoCapture`/`SVBCloseCamera`. For `ctypes`, SDK functions used were `int` return; `SVBGetVideoData` takes `int id, void *buffer, long bytes, int wait_ms`. Reference the installed SDK headers as ground truth when coding.
4. Controls: `SVBSetControlValue(id, 0, gain, auto=0)` and `SVBSetControlValue(id,1, exposure_microseconds,auto=0)`; read back actual values. Preserve settings when appropriate. Exposure quantization is real (50 ms request → 50.148 ms observed).
5. **Observed pitfalls:** skipping camera-info before open gave SDK error **2**; second stop/restart stream in one open session gave frame-wait error **11**, but a new session/single stream ran 600 reads with 0 timeouts. Support bounded timeout retries and recovery, not infinite retries or treating SDK return 0 from `start` as proof frames are flowing.
6. Saved RAW16 pixel values sampled were all divisible by 16; **12-bit right-shift 4** produces plausible grayscale and **GRBG 4×4-block RGB** previews (964×545). This is a suitable **initial**, not calibrated or optimized, preview. Capture previews and scientific source pixels must never share a destructive buffer transform.
7. Multi-frame storage proved under one camera stream with periodic `fsync` and readback SHA-256. Performance **20.2 MiB/s measured write** for the stick, so avoid unnecessary huge buffers and frame copies. Unproven SDK bin modes 3 and 4 should not be enabled by default.

## Mount startup, controls and safety

- Port: `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`, **9600 8N1**, via pyserial. Command/query access must be serialized; ASCII `#`-terminated replies. Don't conflate current reported Alt/Az/RA/Dec with true sky pointing.
- On each connection/reconnection (including mount powered up after Pi): await **trustworthy UTC**, send **UTC offset 0**, date/time, and user site **+45.2933°, −75.8571° (east-positive)**; convert to AM3N **west-positive** longitude `+075*51:26`; verify via `:GG#`, `:GC#`, `:GL#`, `:Gt#`, `:Gg#`. Clock/site writes succeeded manually, but **automation hasn't been written**. Pi lacks RTC, so offline boot needs an explicitly trusted browser time or future RTC/GPS, not guessed time. Camera UI can run while mount initialization is pending.
- Tested manual moves `:Me#`, `:Mn#` and `:Rv120.00#`; directional `:Qe#`/`:Qn#` and `:Q#` stops. **After stopping, mount can report ~1′28″ extra travel before settling**. Never mark stopped solely because `:Q#` was sent; poll repeatedly until the mount reports non-slewing and positions have settled. A Python `finally` block **is not** a crash/USB-link fail-safe.
- **`:hC#` Home works**, including its characteristic route near the zenith (owner says hand controller takes the same route). Final reported altitude/azimuth 0/0 and `H` home flag. This is NOT sky alignment and does not imply safe clearance with every OTA/cable layout.
- `:GAT#` returned undocumented `e7#`; don't infer tracking from it. **Park, tracking and sky GoTo untested.** Avoid automated long slews or night tracking until physical clearances, protocol acknowledgments and stop path have been verified for those commands.
- Physical safety: reachable hand-controller Cancel or power interrupt for tests, no cable snag or tripod collision. AM3N M12 counterweight-hole overlong-bolt risk (can reach internal wiring).
- Operator lease: when operator releases arrow/connection drops/lease expires, immediately request Stop; safe timeout and serial queue still needed if browsers are multiple.

## Offline atlas and image output

- Keep sky data and VirtualSky assets served **locally**. Use standard schematic chart markers and object labels rather than astrophotographs. Search all objects even if chart rendering filters by zoom. Keep VirtualSky behind an adapter.
- FITS is a **planned output format**; current probe files are headerless `.raw16` and must not be mislabeled as FITS. Preserve highest-quality sensor values and useful acquisition metadata; previews are disposable 8-bit encodings.
- Saving individual exposures is optional in UI, but if saving enabled and the USB UUID is missing/full, **report failure** rather than writing to OS microSD. Background sequences continue even if browsers disconnect; this requirement applies to capture, **not to continuous manual movement**.

## Implementation order and verification gates

1. **Project skeleton:** tracked Flask status page, UUID checks and Pi browser smoke test verified 2026-10-27. Camera SDK preview work is the current Pi-test gate; add persistent logging and systemd later. No Home/GoTo on startup.
2. **Camera live preview:** single SDK owner, control readbacks, image byte handling, GRBG 8-bit preview, lightweight streaming to several browsers. Measure CPU/RAM/latency instead of assuming the probe PNG algorithm is sufficiently fast.
3. **Recording:** single RAW/FITS saved exposure, then sequences, USB-UUID checks, checksums/atomic writes, optional saving, uninterrupted capture after browser refresh.
4. **Mount basics:** USB connect/reconnect, time/site verification, status/coordinates, manual jog with deadman Stop, lease enforcement, cautious Home/Park testing.
5. **Offline atlas and pointing:** OpenNGC + Messier and VirtualSky, North/Level, manual two-star / multi-star refinement, chart GoTo, Alt/Az tracking tests *under the real sky*.
6. **Field acceptance:** offline network/time workflow, actual telescope/cables and battery power, long exposure metadata, recoveries from deliberate safe USB disconnects and missing data drive.

**Development discipline:** At each successful milestone, commit source and update a **short** verified/pending note. Do not turn HARDWARE.md into another 69 KB console transcript. Retain full diagnostics locally or rely on Git history. Never invent test results, port mappings or API semantics.
