# AstroPi hardware reference

Current verified hardware and protocol facts (updated 2026-10-31). Older detailed probe logs are in [Git history](https://github.com/Arnbargler/astropi/blob/f01ae019f9ba840f90b5bb5e566d0fc17dab41b7/HARDWARE.md); they are not current setup instructions.

## Devices and installation

| Device | Verified configuration |
| --- | --- |
| Host | Raspberry Pi 4B Rev 1.5, 4 GiB; Debian 13 Trixie ARM64, Python 3.13; hostname `astropi`, login `arn` |
| Camera | SVBONY SV705C, USB ID `f266:9a0a`, USB3 5000M, GRBG, 3856×2180, 12-bit sensor |
| Mount | ZWO AM3N firmware 1.8.8, USB ID `03c3:4001`, CDC ACM serial 9600 8N1, Alt/Az |
| Recording | 64 GB USB3 ext4 stick, `/media/astropi-data`, label `astropi-data`, UUID `25b33cfa-b178-4b86-8a15-d00c8305cca5` |
| Time | systemd NTP; Pi has no battery RTC. AM3N automatic UTC sync is active only when Pi NTP is confirmed |

AM3N stable serial alias: `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`; Pi user belongs to `dialout`. Do not depend on shifting `/dev/ttyACM*` numbers. SVBONY SDK 1.13.4 at `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so` (or `ASTROPI_SVB_SDK`). Camera USB permissions: `/etc/udev/rules.d/90-ckusb.rules`. Vendor binaries are not in Git.

## Wireless network (field result 2026-10-31)

- **AstroPi radio:** BrosTrend AC5L USB (`0bda:c811`,
  Realtek RTL8821CU, `rtw88_8821cu` in-kernel driver on
  `6.18.39+rpt-rpi-v8`, firmware `24.11.0`).
  Uses USB 2.0 and needed no vendor DKMS installation.
  Its NetworkManager profile `Bazingas-Minions-USB` is
  autoconnect enabled, MAC-bound to `74:19:f8:17:b1:f5`,
  with route metric **100**. Earlier 5 GHz signal was
  −44 dBm through the upstairs AP; the Pi's internal
  Wi-Fi was about −59 dBm and had metric **600**.
- **Internal Pi radio:** Operator requested boot option
  `dtoverlay=disable-wifi` to save energy; **a verifying
  post-overlay reboot/interface report is still missing**.
  It could leave the USB interface named `wlan0` instead
  of `wlan1`. Verify/recover as detailed in SETUP.md.
- **Desktop client:** **HP EliteDesk 800 G5 Mini**
  (i5-9500T, 16 GB RAM), replacing the previous n100;
  using a second external BrosTrend Wi-Fi adapter.
  Exact desktop Wi-Fi driver, link rates and OS version
  were not supplied for this observation.
- **Preview result:** Original internal-wireless setup
  suffered intermittent ~0.5–1 s browser JPEG pauses,
  whereas direct Ethernet was smooth. With the
  EliteDesk and external adapters on both ends, the
  operator describes Wi-Fi preview as **indistinguishable
  from direct Ethernet**. No change to the camera,
  Flask or JPEG delivery code was required; this does
  **not independently identify the faulty older component**
  or prove future performance at all outdoor distances.
  AstroPi remains in **Station Mode**, not hotspot/AP
  mode, and no permanent Ethernet is planned.

The camera SDK and USB RAW/FITS recording operate on the
Pi independently of browser JPEG receipt. Network latency
can still affect operator mount commands; keep the backend
deadman and physical hand-controller/power fallback.

## SV705C integration quirks

- **Binning:** SV705C manufacturer's specifications and manual explicitly
  list **1×1 and 2×2** only. An earlier SDK probe listed 1/2/3/4
  capability values but 3×3 and 4×4 are NOT claimed as supported on this
  camera. `SVBSetROIFormat` accepts **post-binning** output dimensions:
  3856×2180 at bin=1, 1928×1090 at bin=2. It must be set before video
  capture starts; switching binning closes the old SDK camera session and
  opens a new one. 2×2 RAW16 is 4,203,040 bytes. **2×2 RAW/FITS was
  confirmed on the actual Pi**: user saved a ~4 MiB binned frame and
  viewed the FITS successfully in Siril (2026-10-28).
  Sony's IMX585 datasheet (page 38) describes 2×2 adjacent-pixel
  **Bayer-preserving colour output**:
  [sensor datasheet](https://dl.khadas.com/products/add-ons/cameras/imx585/datasheet/imx585-datasheet.pdf).
  Accordingly 2×2 preview and JPG/PNG quicklooks use GRBG colour
  when Debayer is On, and green-site monochrome when Off; the same
  behaviour applies to 1×1. **On 2026-10-28 the operator confirmed that
  2×2 colour preview renders correctly on the real SV705C** (visual field
  verification). JPG/PNG quicklooks use the same GRBG interpretation;
  a separate saved-quicklook colour check is not recorded. The FITS writer
  currently omits `BAYERPAT` for 2×2, the read-only verifier expects
  this omission, and the saved `metadata.json` still says
  `"bayer": "unverified at 2x2"`. This older **metadata** behaviour
  does not undo the verified colour *preview*. Changing it requires
  its own writer/verifier/tests update. RAW16 bytes and FITS numeric
  pixels remain unaltered.
  See [SVBONY published specs](https://www.svbony.com/products/sv705c-color-planetary-camera-imx585).
- Required flow: enumerate, call `SVBGetCameraInfo` to obtain real CameraID (do not hard-code), open, set full-frame 3856×2180 ROI and RAW16 enum 4, **start one continuous stream**, read frames, restore controls and close on exit. An earlier stop/start in the same SDK session returned timeout code **11**.
- Gain is SDK control **0**; exposure is control **1** in microseconds. The operator has tested the expanded browser gain presets **0, 50, 100, 260, 350, 450, 550, 650** and reports the expected visible image response. This is **not** an independently confirmed SDK gain maximum or calibrated HCG transition. SDK readback rounds values: 10,000→10,007 µs, 50,000→50,148 µs and 1,000,000→1,000,143 µs. Image brightness responded to changes. No photometric calibration claim.
- RAW16 frame = **16,812,160 bytes**, 3856×2180 little-endian uint16, with 12-bit Bayer **GRBG** values shifted left by four bits. FITS stores full-resolution native samples (big-endian BITPIX16, BZERO=32768, BSCALE=1); RAW16 unchanged. FITS exposure start is estimated, not a hardware timestamp. Browser preview ~964×545 at either binning level; saved JPEG/PNG quicklooks are 1928×1090 at 1×1 or 964×545 at 2×2. These are *not* calibrated full demosaics.
- Pi 50ms live rates: RAW acquisition ~15.8 FPS; colour preview ~14.8 FPS (62ms processing); sampled-green mono ~16.6 FPS (14ms processing).
- **Standalone 20-minute endurance probe**: 600/600 full RAW frames retrieved, 120/120 saved/verified by SHA-256 (~1.88 GiB), zero SDK timeouts, CPU 46.7–51.6°C, throttled flags 0x0. One camera USB3 reset was logged near startup without observed lost frames. This probe is *not* proof of equivalent 120-frame browser recording endurance.
- **Browser captures**: 11/11 file size/hash matches across four format combinations; independent full-frame FITS↔RAW16 check matched all 8,406,080 samples. Pi sequences of 5 and 10 frames completed; a 10-frame request cancelled at 4/10 with zero incomplete directories.
- USB recording mount must match its UUID before and during each save. Files are written via pinned directory fds, fsync and atomic `.partial` → final directory rename. **Never fall back to system microSD.** Missing-drive and in-flight device-loss handling have not been deliberately field-failure-tested.

## AM3N serial control

AM3N read queries: `:GVP#` model (AM3N), `:GV#` firmware (1.8.8), `:GU#` state, `:GA#` altitude, `:GZ#` azimuth, `:GR#` RA, `:GD#` Dec and `:GS#` sidereal time. Status flags are optional and shift position: `n` not tracking, `N` not slewing, `H` Home, `Z` Alt/Az. `M...` suffix is undocumented; preserve raw status. Reported RA/Dec are **not verified sky pointing**.

### Current browser manual rates

| UI | Serial rate | Nominal multiple |
| --- | --- | ---: |
| Slow | `:R5#` | 8× |
| Medium | `:Rv20.00#` | 20× |
| Fast | `:Rv60.00#` | 60× |
| Slew | `:R8#` | 720× |
| Max | `:R9#` | 1440× |

These rates follow known AM-series driver commands; exact angular speeds have not been measured. Direction commands `:Mn#`, `:Ms#`, `:Me#`, `:Mw#`; all-stop `:Q#`. Operator verified manual jogging, release-to-Stop and camera/mount coexistence; slow-speed 3s automatic stop was previously tested, then **deliberately removed**. Current app supports direct hold-to-move with **no fixed duration limit**, 600ms missing-heartbeat Stop, one serial-owner thread and post-Stop position settling before next jog. Serial loss/crash cannot guarantee a physical stop; manual Cancel/power remains fallback.

**Permanent observing site:** **45.2933° N, 75.8571° W**
(east-positive longitude −75.8571°). User-approved permanent coordinates.
On every explicit Connect, AstroPi checks Pi NTP and sets **both** mount
UTC clock and site, then verifies ACKs and readbacks. Site setters are
whole-arcminute `:St+45*18#`, `:Sg075*51#`; the atlas retains the
more precise values. Firmware 1.8.8 previously rejected `:MS#` with
`e7` (*time/location not set*) until AstroPi began reasserting the
permanent site along with UTC. There is also a manual **Sync Time / Site**
button. Failed sync locks native GoTo, not manual jog. No arbitrary
location/time input; don't add one without an explicit user decision.

**AM3N UTC:** after NTP reports synchronized, send
`:SG+00:00#`, `:SCMM/DD/YY#`, `:SLHH:MM:SS#`, each requiring
acknowledgement; verify with `:GG#`, `:GC#`, `:GL#` against Pi UTC
(within six seconds). Mount display time is UTC, **not Ontario local**.
This is mount-specific; the offline atlas intentionally trusts Pi UTC
without an NTP check or warning. There is no RTC or manual-time mode.

**GoTo:** catalogue-only J2000→date coordinates via `:Sr#`,
`:Sd#`, `:MS#`. **Real AM3N test on 2026-10-31:** the M40 slew
moved in the expected Alt/Az direction and finished at mount-reported
coordinates. The user interrupted an M45 slew successfully with global
`:Q#` STOP. This does **not** verify optical pointing accuracy.

**Tracking:** `:GAT#` (reply `0` OFF, `1` ON), `:Te#` ON,
`:Td#` OFF. User repeatedly verified both controls and UI confirmation
on real AM3N firmware 1.8.8. The mount reported tracking **ON**
immediately after Connect; AstroPi does not enable/disable it during
Connect or GoTo. During hand-controller Home the mount returned
`:GAT#` error `e5` while it nevertheless moved Home successfully;
display UNKNOWN and the diagnostic, not a false tracking state.

**Native Home:** standalone terminal probe previously verified `:hC#`
could reach 0°/0° via a near-zenith/wrapped-azimuth path. The app now
offers explicit **Az Home** (both axes, Alt/Az mode only, tracking OFF):
serialized `:hC#` without ACK, then `:GU#` Home flag `H` and no-slew
flag `N` confirmation; global STOP can interrupt. **The new browser
Az Home workflow has not yet been field-tested.** This is neither
Park (`:hP#`) nor Set Home nor optical alignment. Physical
North/Level is a separate operator-confirmed tripod/base setup.

**Hardware caution:** the AM3N M12 counterweight hole can reach
internal wiring with an overlong bolt. Never insert an overlong bolt.

## Browser UI field check

On 2026-10-28 the operator confirmed the **Focus / Find / Fotograph**
three-tab layout works as expected on the actual Pi, including the
revised gain controls. This does not independently test emergency Stop
under injected faults, telescope pointing, or extended recording after
the UI refactor. The user subsequently verified VirtualSky target selection and popup
behaviour, GoTo M40, global STOP during GoTo M45, repeated tracking
ON/OFF and North/Level confirmation on the real Pi. **Az Home button
and optical two-star alignment remain unverified/unimplemented,
respectively.**

## Not verified / future

No true optical star alignment, optical pointing accuracy, Park,
plate solving, hardware-validated Az Home **browser** workflow, controlled
forced USB/serial-loss fail-safe test, field battery/buck wiring,
mounted-telescope clearance, service auto-start or no-NTP mount recovery.
Do not treat simulated tests or standalone probes as proof of a
browser feature's real-hardware behaviour.
