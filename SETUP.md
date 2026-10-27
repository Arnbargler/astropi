# AstroPi — current camera preview setup (2026-10-27)

## Verified state

AstroPi uses a Raspberry Pi 4 (4 GiB), SVBONY SV705C (USB3), and ZWO AM3N
(Alt/Az). The Pi has already run the browser status UI and live colour preview.
Fixed stretch showed that gain and exposure both affect the camera as expected.

This newer preview-performance and controls iteration is **software-tested but
not yet Pi-tested**. Mount motion/GoTo/tracking and full RAW/FITS recording are
not implemented. The browser is for a trusted local network only.

## Updating and running

In the currently running Flask terminal, stop the old server with **Ctrl+C**.

    cd ~/astropi
    git pull --ff-only
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    python run.py --host 0.0.0.0 --port 8080

Browse to http://astropi.local:8080/ or the Pi's LAN address. Hard-refresh
with **Ctrl+Shift+R** to ensure the latest JavaScript/CSS loads. The server
still runs as a foreground development process, not a systemd service. Do not
forward the port to the Internet.

Choose **Take Control**, then **Start preview**. Other browser viewers can
watch the same JPEG but cannot change camera settings without the operator
lease.

## Controls

- Exposure uses 18 native radio inputs styled as buttons: 1, 2, 5, 10, 25,
  50, 100, 250, 500, 750 milliseconds, then 1, 2, 5, 10, 15, 20, 25, 30
  seconds.
- Gain buttons: 0, 5, 10, 20, 30, 50, 75, 100.
- Clicking EITHER an exposure or gain button automatically submits both current
  selected values. No **Apply** button. Requested selections stay highlighted
  while waiting for the SDK. The "Actual" fields report SDK readbacks.
- **Stretch A/F**: Auto adaptive brightness stretch, or Fixed brightness scale.
- **Debayer On/Off**: On = sampled GRBG colour JPEG, Off = faster grayscale JPEG
  using the green photosites of the raw Bayer mosaic. Both modes still acquire
  original full 3856×2180 RAW16 frames. Neither saves or modifies source RAW16.

## Performance design

There is no longer any 250-ms artificial preview delay. One thread exclusively
owns the SVBONY SDK and acquires RAW16 frames. A second thread reads immutable
copies from a one-frame mailbox and produces reduced-resolution JPEGs. It
drops outdated frames whenever processing falls behind, bounding memory use.
Preview colour uses simplified GRBG averaging and precomputed stretch lookup
tables; monochrome bypasses colour reconstruction entirely.

The browser checks for new preview sequence numbers every **50 ms**, retrieving
only newly generated JPEGs. The displayed RAW FPS, JPEG FPS and processing
time are separate metrics. The Pi's actual CPU, USB and exposure time determine
the achievable rates; no speed guarantee until measured on hardware.

The backend coalesces rapid exposure/gain clicks, retaining only the newest
pending pair. A 30-second in-flight exposure may delay applying the next
setting or honoring Stop by up to its exposure/read timeout plus margin.
Start performance testing at **50 ms or 100 ms** exposure and compare Debayer
On versus Off, including the Pi temperature.

The camera may show SDK code 11 on some stop/restart cycles, as previously
observed in the separate hardware tests. Do not repeatedly unplug/reset it
without checking the error. The mount is NEVER moved by this web application
at its current development stage.

Read README.md, REQUIREMENTS.md, HARDWARE.md, and DEVELOPMENT.md for scope,
exact hardware setup, important tested behaviour, and remaining work.
