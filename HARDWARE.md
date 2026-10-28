# AstroPi hardware reference

Current verified hardware and protocol facts (2026-10-28). Older detailed probe logs are in [Git history](https://github.com/Arnbargler/astropi/blob/f01ae019f9ba840f90b5bb5e566d0fc17dab41b7/HARDWARE.md); they are not current setup instructions.

## Devices and installation

| Device | Verified configuration |
| --- | --- |
| Host | Raspberry Pi 4B Rev 1.5, 4 GiB; Debian 13 Trixie ARM64, Python 3.13; hostname `astropi`, login `arn` |
| Camera | SVBONY SV705C, USB ID `f266:9a0a`, USB3 5000M, GRBG, 3856×2180, 12-bit sensor |
| Mount | ZWO AM3N firmware 1.8.8, USB ID `03c3:4001`, CDC ACM serial 9600 8N1, Alt/Az |
| Recording | 64 GB USB3 ext4 stick, `/media/astropi-data`, label `astropi-data`, UUID `25b33cfa-b178-4b86-8a15-d00c8305cca5` |
| Time | systemd NTP; Pi has no battery RTC. AM3N automatic UTC sync is active only when Pi NTP is confirmed |

AM3N stable serial alias: `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`; Pi user belongs to `dialout`. Do not depend on shifting `/dev/ttyACM*` numbers. SVBONY SDK 1.13.4 at `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so` (or `ASTROPI_SVB_SDK`). Camera USB permissions: `/etc/udev/rules.d/90-ckusb.rules`. Vendor binaries are not in Git.

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
  Accordingly 2×2 preview and JPG/PNG quicklooks now support GRBG colour
  when Debayer is On, and green-site monochrome when Off; the same
  behaviour applies to 1×1. **The exact output Bayer phase GRBG is a
  provisional SDK assumption, not yet colour-target-verified on the Pi**.
  FITS still omits `BAYERPAT` for 2×2 until that check; both RAW16 bytes
  and FITS numeric pixels remain unaltered.
  See [SVBONY published specs](https://www.svbony.com/products/sv705c-color-planetary-camera-imx585).
- Required flow: enumerate, call `SVBGetCameraInfo` to obtain real CameraID (do not hard-code), open, set full-frame 3856×2180 ROI and RAW16 enum 4, **start one continuous stream**, read frames, restore controls and close on exit. An earlier stop/start in the same SDK session returned timeout code **11**.
- Gain is SDK control **0**; exposure is control **1** in microseconds. SDK readback rounds values: 10,000→10,007 µs, 50,000→50,148 µs and 1,000,000→1,000,143 µs. Image brightness responded to changes. No photometric calibration claim.
- RAW16 frame = **16,812,160 bytes**, 3856×2180 little-endian uint16, with 12-bit Bayer **GRBG** values shifted left by four bits. FITS stores full-resolution native samples (big-endian BITPIX16, BZERO=32768, BSCALE=1); RAW16 unchanged. FITS exposure start is estimated, not a hardware timestamp. Browser preview ~964×545, JPEG/PNG saved quicklooks 1928×1090; these are *not* calibrated full demosaics.
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

**Stored observing site:** latitude **+45.2933° N**, `+45*17:36`; longitude **−75.8571° east-positive** (AM3N convention west-positive `+075*51:26`). Currently read-only in app. Standalone site setters `:St+45*17:36#` and `:Sg+075*51:26#` previously returned success; **current app does not set site**.

**Automatic clock sync on each explicit Connect:** check `timedatectl show -p NTPSynchronized --value` equals yes; send `:SG+00:00#`, `:SCMM/DD/YY#`, `:SLHH:MM:SS#`, require single-byte `1` acknowledgment from each; read back with `:GG#`, `:GC#`, `:GL#` and compare within six seconds of Pi UTC. **Confirmed on live firmware 1.8.8**: 2026-10-28, mount UTC time 08:47:34, offset +00:00, existing site unchanged. UI says **Mount time (UTC)**; it is intentionally not Ontario local time. If NTP not yet synchronized, report error and retry on a later Connect. No manual-time field mode yet.

**Standalone native Home test**: `:hC#` reached altitude/azimuth 0/0 via near-zenith/azimuth-wrap; this is not alignment and **Home is not implemented in browser**. Park `:hP#`, sky GoTo and tracking have not been validated. The AM3N M12 counterweight bolt hole can reach internal wiring with an overlong bolt: do not insert one.

## Not verified / future

No true optical sky alignment, GoTo, tracking, Park, automatic site overwrite or plate solving. No controlled forced USB/serial-loss fail-safe test, real field battery/buck wiring, mounted telescope clearance, service auto-start or no-NTP clock recovery. Do not infer SDK-only or terminal-probe tests imply application features.
