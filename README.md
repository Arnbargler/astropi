# AstroPi — project handoff

**Status (2026-10-27): SV705C preview and colour/mono frame rates VERIFIED on Pi. One-shot RAW16/FITS/JPG/PNG capture successfully created selected formats on the real Pi USB drive in four separate capture directories; recorded file sizes and SHA-256 checksums verified on Pi (11/11 files); Real four-format FITS file passed independent full-frame Bayer pixel comparison against RAW16. Five-frame and ten-frame exposure sequences completed on Pi; cancelling another ten-frame request stopped after four completed frames, with zero incomplete directories. First read-only AM3N mount serial connection, status and reported-coordinate dashboard is newly code-tested but awaits on-Pi verification. No mount movement, tracking, Home, GoTo or automatic clock/site setters have been implemented; longer capture endurance and USB faults remain unverified.** AstroPi is a Raspberry Pi 4-hosted, browser-operated deep-sky camera and telescope controller for one SVBONY SV705C and one ZWO AM3N mount, operating in **Alt/Az only**.

This private GitHub repository is the durable handoff for a **new AI assistant or development session**. Do not infer that a tested terminal script is a committed application: **live camera preview and one-shot USB file creation are Pi-verified; five-/ten-frame recording, cancellation after four saved frames, and FITS/RAW16 pixel equality are Pi-verified; extended capture endurance, USB-loss recovery and first AM3N read-only telemetry hardware test remain outstanding**.

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

**Current next gate:** sequence completion and cancellation have passed on Pi. A NEW read-only AM3N connection and telemetry panel is software-tested; next verify it on Pi before considering motion controls. USB-loss/fault handling and browser-disconnect endurance remain outstanding. Read [SETUP.md](SETUP.md) for actual tests. Review the full scope in [REQUIREMENTS.md](REQUIREMENTS.md) before selecting frameworks.

**Don't repeat completed hardware probes by default.** Don't claim more than was tested. In particular, Home ≠ alignment, RAW16 ≠ FITS, successful SDK exposure *readback* ≠ precise exposure calibration, and the offline/no-RTC time problem is still open.

## Operating assumptions

- The Pi performs acquisition, camera processing, mount control and web serving. The Linux Mint **N100** is optional for development/browser access and **post-capture stacking/field-rotation correction**, not an always-required server.
- **Offline sky chart and catalogues**, manual two-/multi-star alignment, no plate solving, no live stacking, no Internet dependency for the chart.
- Multiple browser viewers, **one controller lease**; a disconnected browser must **never leave a continuous manual slew running**. Camera capture sequences continue after browser disconnect.
- Trusted home/field local network only; no user accounts or Internet-facing service planned.
- Do not commit private credentials, SDK binaries or large captured RAW/FITS data.

**Suggested new-session opener:** “Continue AstroPi from the private GitHub repository `Arnbargler/astropi`. Read README, REQUIREMENTS, HARDWARE and DEVELOPMENT in that order. The live camera preview works on Pi; the one-shot RAW16/FITS/JPG/PNG saver produced four real capture folders on Pi USB; the 11 saved files passed size and SHA-256 checks; the prior four-format FITS file passed full Bayer pixel equality with RAW16 and a five-frame FITS+JPG sequence completed on Pi; ten-frame completion and four-frame cancellation are now verified; next verify the newly implemented AM3N read-only status panel on real Pi serial, then cautiously address mount safety. Preserve the single camera SDK owner, storage UUID checks, and untested mount safety boundaries.”
