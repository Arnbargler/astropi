# AstroPi

Observatory controller running on a **Raspberry Pi 4B (4 GB)** with Debian 13
Trixie, one **SVBONY SV705C** camera and one **ZWO AM3N** Alt/Az mount.
Flask serves a trusted-LAN browser application on port **8080** (Pi Wi-Fi
IP or `astropi.local`). The Pi owns camera acquisition, mount serial
I/O and captures; the desktop/browser is only a client.

## Working state — 2026-10-31

**Previously implemented and operator-tested on the Pi:** the persistent
**Focus / Find / Fotograph** three-tab interface. Tabs do not reload the
page or restart hardware sessions.

| Tab | Available now | Not yet available |
| --- | --- | --- |
| **Focus** | Shared live preview and SV705C settings | Digital zoom, star-centred ROI, peaking, HFR/focus graph |
| **Find** | Offline VirtualSky, 110 Messier targets, selection and live calculated Alt/Az/horizon visibility | Alignment, enabled GoTo, tracking and full NGC/IC search |
| **Fotograph** (default) | Full camera preview/settings, capture formats/counts, USB/host status | Stacking and other deferred imaging tools |

The shared **Mount Controls** button in the sticky status bar slides a
single **right-side overlay drawer** in/out from *any* tab. The drawer
contains the existing AM3N Connect, telemetry, manual jog, clock/site and
speed controls. It does **not resize** the camera preview or atlas, and
remains open when changing tabs. No pin/dock mode yet. **STOP MOUNT** and
global camera/mount/capture status remain visible above the drawer,
including to viewers. Closing the drawer or changing tabs during a held
jog requests Stop; idle closing/tab switching does not. The *same* preview
and settings DOM moves between Focus and Fotograph. Switching tabs keeps
the operator lease, camera stream and Pi-owned captures. Existing Pi-side
deadman and Stop verification remain in force; physical Cancel/power
is the last resort.

**Preview delivery:** Two alternating JPEG image elements keep the last
successful frame visible, skip superseded frames and avoid concurrent
image loads. Browser-side request ordering ignores stale camera status
responses. These correctness fixes remain in the code.

**Field networking — resolved 2026-10-31:** AstroPi remains in
**Station Mode** on the existing 5 GHz home Wi-Fi. The Pi uses its
BrosTrend AC5L USB adapter (Realtek `0bda:c811`, built-in
`rtw88_8821cu` driver), with the MAC-bound NetworkManager profile
`Bazingas-Minions-USB` set to autoconnect and route metric **100**.
The operator replaced the n100 development client with an
**HP EliteDesk 800 G5 Mini**, using another external BrosTrend
Wi-Fi adapter. **Live preview is now visually indistinguishable
from direct Ethernet**, with no camera-code change. The earlier
~0.5–1 s pauses were associated with the old wireless path;
individual contributions from the old PC, radios and access point
were not separately measured. See [HARDWARE.md](HARDWARE.md).

The Pi's onboard Wi-Fi was slated for disabling using
`dtoverlay=disable-wifi` to save power; **a post-change interface
listing has not been provided**, so do not assume this has been
verified. See [SETUP.md](SETUP.md) for how to check or recover via
Ethernet. IP addresses are DHCP-assigned. Keep functional browser
preview safeguards (two JPEG buffers, stale-response ordering);
remove/reintroduce no temporary network timing probes. Pi-owned
RAW/FITS science captures and USB recording are independent of
browser image delivery.

### Camera and recording

- Sensor **3856×2180**, native 12-bit GRBG in RAW16. Supported hardware
  binning: **1×1 / 2×2** (1928×1090), switched through a fresh SDK
  session. Operator verified correct **2×2 colour preview** on the SV705C.
  RAW/FITS saves and binned FITS viewing in Siril were also field-tested.
- Exposure presets **1 ms–30 s**; gain buttons
  **0, 50, 100, 260, 350, 450, 550, 650**. Operator reports the revised
  gain settings produce expected visible changes. SDK's actual maximum
  and sensor HCG threshold have not been independently measured.
- Debayer **On/Off**, fixed/automatic preview stretch and sparse raw-signal
  statistics; there is **no histogram or white-balance control** yet.
- Independent format switches **FITS, RAW16, JPG, PNG** and capture buttons
  **1, 5, 50, 100, 150, 200, Cancel**. Sequences are Pi-owned and continue
  when the browser closes, **not after a Pi/Python restart**.
- Captures require the **verified USB data filesystem UUID**. SHA-256
  manifests, preflight checks, fsync and atomic publication protect output;
  **never fall back to the system microSD**. Independent FITS/RAW16 pixel
  verification is available. Binned FITS currently omits `BAYERPAT`;
  binned capture manifests still say `"unverified at 2x2"` despite the
  visually verified *preview*. Neither metadata path has been changed.

### Mount and clock

AM3N manual N/S/E/W press-and-hold with five speeds
(**8× / 20× / 60× / 720× / 1440×**), release-to-Stop, a **600 ms**
lost-heartbeat Stop and motion-settling checks. No arbitrary jog
duration limit. A viewer can request emergency Stop without the operator
token. Mount serial is owned by one backend worker.

On explicit Connect, the Pi requires NTP synchronization before sending
UTC date/time to the mount; ACKs and readback are checked. Failure is
reported, not disguised. The mount-stored **permanent observing site**
is **+45.2933° N, −75.8571° east-positive** (75.8571° W).
It is **read-only** in AstroPi. Reported RA/Dec are *not* verified
optical pointing; there is **no alignment, GoTo, tracking control,
Home or Park** in the browser.

## Offline VirtualSky atlas in Find — implemented in code

VirtualSky **v0.7.7** is bundled locally in the persistent **Find** tab.
The sky is a schematic map (no images or CDN) with horizon/cardinals,
pan, detail zoom, constellation labels/lines, a toggleable RA/Dec grid,
stars and planets. Search `M1`–`M110` or click a Messier marker to
show the object's name, RA and Dec and centre a detail view. **Find stage 1**
also calculates selected-object **altitude, azimuth (true north = 0°)
and above/below geometric horizon** from Pi UTC and the fixed site.
The dedicated `coordinates.js` module precesses catalogue J2000
RA/Dec to mean equator/equinox of date, then calculates local Alt/Az.
This is a **planning estimate**: no refraction, local obstructions,
mount alignment or mechanical clearance. The readout updates with
the sky clock without querying or controlling the mount. **Chart
selection never sends a mount command.** A separate GoTo button
is present but **disabled** until later stages.

The atlas uses the fixed site **45.2933° N, −75.8571° east-positive**
and Pi UTC from existing `/api/status`, fetched on entering Find and
corrected on normal polling. **No atlas NTP validation or warning** (this
is a deliberate operator choice); mount Connect retains its existing
separate NTP verification. VirtualSky loads its star, planet, line,
English-label and Messier assets under
`astropi/static/vendor/virtualsky/`. The adapter is
`astropi/static/atlas.js` and position helper `astropi/static/coordinates.js`; provenance/permission notes are in
`astropi/static/vendor/virtualsky/PROVENANCE.md`.

**Status:** implemented in Git; GitHub CI exercises offline asset, UTC, geometric coordinate, chart-interaction and DOM
regressions. Browser appearance/interaction on the **actual Pi** have
not yet been reverified by the operator. Full OpenNGC, precise pointing
marker, alignment, GoTo and focus tools remain deferred.

## Operate and continue development

Start/update the Pi and run verification using [SETUP.md](SETUP.md).
Quick launch (after stopping the previous process safely):

```bash
cd ~/astropi
git pull --ff-only
source .venv/bin/activate
python run.py --host 0.0.0.0 --port 8080
```

The Flask development server is **trusted LAN only**, not Internet-facing.
No systemd auto-start service is installed. No camera or mount operation
starts merely because the page loads.

**Read in order for a new AI instance:**

1. **README.md** — verified current state and the immediate next task.
2. **REQUIREMENTS.md** — selected scope, including deferred features.
3. **HARDWARE.md** — real devices, SDK/protocol quirks and field evidence.
4. **DEVELOPMENT.md** — file ownership, invariants, VirtualSky plan/tests.
5. **SETUP.md** — Pi operation and diagnostics.

Git history holds old experiments. Do not resurrect superseded behaviour
(such as the old camera stop/restart workaround or mount jog time limits)
from historical notes.
