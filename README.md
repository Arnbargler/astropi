# AstroPi — project handoff

**Status (2026-10-28): SV705C preview and colour/mono frame rates VERIFIED on Pi. One-shot RAW16/FITS/JPG/PNG capture successfully created selected formats on the real Pi USB drive in four separate capture directories; recorded file sizes and SHA-256 checksums verified on Pi (11/11 files); Real four-format FITS file passed independent full-frame Bayer pixel comparison against RAW16. Five-frame and ten-frame exposure sequences completed on Pi; cancelling another ten-frame request stopped after four completed frames, with zero incomplete directories. First AM3N read-only browser serial connection, model/firmware and reported coordinates are now Pi-verified. The optional Alt/Az status-flag correction and browser Disconnect/Reconnect, with cleared/restored coordinates, are now verified on the real Pi. First Pi screenshots show AM3N manually reported azimuth changed from 000°00′00″ to 000°05′57″ with the browser reporting stable axes after Stop. Following the controlled post-reboot E-jog check, the operator reports movement, release-to-stop and stability all behaved as expected. No precise measured hold/delta is available; North and South jogs have now also been confirmed by the operator to work and stop as expected at the deliberately slow test speed. The 3-second hard jog limit is now physically verified: the user held a direction continuously, saw Stop requested and observed the mount stop automatically. The separate 600ms missed-heartbeat path, West motion and faster speed presets remain hardware-unverified. Home, GoTo, tracking and automatic clock/site setters are still unimplemented; abnormal USB-loss safety remains unverified.** AstroPi is a Raspberry Pi 4-hosted, browser-operated deep-sky camera and telescope controller for one SVBONY SV705C and one ZWO AM3N mount, operating in **Alt/Az only**.

This private GitHub repository is the durable handoff for a **new AI assistant or development session**. Do not infer that a tested terminal script is a committed application: **live camera preview and one-shot USB file creation are Pi-verified; five-/ten-frame recording, cancellation after four saved frames, and FITS/RAW16 pixel equality are Pi-verified; extended capture endurance, USB-loss recovery and AM3N forced serial-loss and missing-serial recovery tests remain outstanding**.

## Read in this order

1. **[README.md](README.md)** — orientation, exact current status and next step (this file).
2. **[REQUIREMENTS.md](REQUIREMENTS.md)** — *authoritative* feature decisions and explicit exclusions. Preserve the numbered decisions.
3. **[HARDWARE.md](HARDWARE.md)** — *authoritative* current hardware inventory, verified protocols, paths, test evidence and unresolved risks.
4. **[DEVELOPMENT.md](DEVELOPMENT.md)** — proposed implementation boundaries, integration rules, startup behaviour and build sequence. Architecture is guidance, not code already written.

The extensive **original chronological hardware probe log** is preserved in [Git history at commit `f01ae019`](https://github.com/Arnbargler/astropi/blob/f01ae019f9ba840f90b5bb5e566d0fc17dab41b7/HARDWARE.md). It includes superseded observations; consult only for deep troubleshooting rather than loading it as normal handoff context.

## Verified today

- **Host:** `arn@astropi`, Raspberry Pi 4B Rev 1.5 **4 GiB**, Debian 13.6 Trixie / ARM64, Python 3.13.5. Hardware camera SDK loaded successfully.
- **Camera:** SV705C on USB3; full-size **3856×2180 RAW16** captures; 12-bit values appear left-shifted by four; **GRBG** Bayer. Grayscale and colour PNG previews inspected and accepted. Exposure and gain controls produce expected image response.
- **Mount:** ZWO **AM3N firmware 1.8.8**, 9600-baud USB serial; clock/site commands, both motors, commanded stop settling and native `:hC#` Home all tested. **No celestial alignment, GoTo, tracking or Park verification yet.**
- **Recording:** 64 GB USB3 stick, ext4 auto-mounted read/write at `/media/astropi-data`; reboot retention and SHA-256 integrity passed.
- **Endurance:** 20 minutes, **600/600 frames received**, **120/120 full RAW16 files saved and checked**, **0 SDK timeouts**, Pi **46.7–51.6°C**, `throttled=0x0`. One kernel USB3 reset occurred near camera initialization; no resulting failures.
- **Observing site:** user-selected **+45.2933° N, −75.8571°** longitude (east-positive). Mount location was updated and read back. Mount UTC clock was set successfully from Pi's NTP-synchronized clock; **automatic reconnection/clock synchronization is not implemented**.

## The next development step

**Current next gate:** sequence completion and cancellation have passed on Pi. The new read-only AM3N connection and coordinate panel has been observed working on real Pi hardware. Browser Disconnect/Reconnect and status clearing have passed on real Pi hardware. The new low-speed manual jog/Stop implementation passes simulated serial tests; first Pi motion screenshots show 5′57″ change in azimuth with the UI reporting stable axes after Stop. The operator subsequently confirmed the controlled E jog and release-to-stop behaved as expected; N/S jog/release worked as expected on the real mount; the Pi's 3-second hard jog cutoff has now passed on the mount. New Slow 8× / Medium 20× / Fast 60× choices are code-tested only; 20×/60× must be tried carefully. Faster settings have shorter 2s/1s absolute caps. The 600ms server deadman and independent 3s hard cap CANNOT guarantee stopping if the Pi or serial connection fails; physical Cancel/power remains essential. USB-loss/fault handling and browser-disconnect endurance remain outstanding. Read [SETUP.md](SETUP.md) for actual tests. Review the full scope in [REQUIREMENTS.md](REQUIREMENTS.md) before selecting frameworks.

**Don't repeat completed hardware probes by default.** Don't claim more than was tested. In particular, Home ≠ alignment, RAW16 ≠ FITS, successful SDK exposure *readback* ≠ precise exposure calibration, and the offline/no-RTC time problem is still open.

## AM3N current manual interface (2026-10-28)

Mount direction buttons now **move on press-and-hold without a separate Arm click**. Operator control is still required. Releasing, changing tab/window, emergency Stop or loss of 600ms heartbeat requests Stop; no fixed duration limit. Repeated presses require Stop/axis settling before a new direction starts.

Available preset commands are **Slow 8x** (`:R5#`), **Medium 20x** (`:Rv20.00#`), **Fast 60x** (`:Rv60.00#`), **Slew 720x** (`:R8#`) and **Max 1440x** (`:R9#`). The final two map directly to the published INDI AM-series driver. The operator reports the three lower presets working on the actual AM3N, while **Slew/Max are code-tested only and await Pi hardware verification**. Clock/site readout remains on-demand and read-only, and Home/GoTo/tracking are not implemented in the browser.

## Operating assumptions

- The Pi performs acquisition, camera processing, mount control and web serving. The Linux Mint **N100** is optional for development/browser access and **post-capture stacking/field-rotation correction**, not an always-required server.
- **Offline sky chart and catalogues**, manual two-/multi-star alignment, no plate solving, no live stacking, no Internet dependency for the chart.
- Multiple browser viewers, **one controller lease**; a disconnected browser must **never leave a continuous manual slew running**. Camera capture sequences continue after browser disconnect.
- Trusted home/field local network only; no user accounts or Internet-facing service planned.
- Do not commit private credentials, SDK binaries or large captured RAW/FITS data.

**Suggested new-session opener:** “Continue AstroPi from the private GitHub repository `Arnbargler/astropi`. Read README, REQUIREMENTS, HARDWARE and DEVELOPMENT in that order. The live camera preview works on Pi; the one-shot RAW16/FITS/JPG/PNG saver produced four real capture folders on Pi USB; the 11 saved files passed size and SHA-256 checks; the prior four-format FITS file passed full Bayer pixel equality with RAW16 and a five-frame FITS+JPG sequence completed on Pi; ten-frame completion and four-frame cancellation are now verified; next verify the newly implemented AM3N read-only status panel on real Pi serial, then cautiously address mount safety. Preserve the single camera SDK owner, storage UUID checks, and untested mount safety boundaries.”
