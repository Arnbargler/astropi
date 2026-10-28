# AstroPi

Observatory controller running on a **Raspberry Pi 4B (4 GB)** with Debian 13
Trixie, one **SVBONY SV705C** camera and one **ZWO AM3N** Alt/Az mount.
Flask serves a trusted-LAN browser application at
`http://astropi.local:8080/`. The Pi owns camera acquisition, mount serial
I/O and captures; the desktop/browser is only a client.

## Working state — 2026-10-28

**Implemented and operator-tested on the Pi:** the persistent
**Focus / Find / Fotograph** three-tab interface. Tabs do not reload the
page or restart hardware sessions.

| Tab | Available now | Not yet available |
| --- | --- | --- |
| **Focus** | Shared live preview and SV705C settings | Digital zoom, star-centred ROI, peaking, HFR/focus graph |
| **Find** | AM3N Connect/Disconnect, telemetry, manual jogging, clock/site display; atlas placeholder | VirtualSky, target selection, alignment, GoTo, tracking |
| **Fotograph** (default) | Full camera preview/settings, capture formats/counts, USB/host status | Stacking and other deferred imaging tools |

Sticky global camera/mount/capture status and **STOP MOUNT** are visible
on every tab, including to viewers. The *same* preview and settings DOM
moves between Focus and Fotograph. Switching tabs keeps the operator lease,
camera stream and ongoing Pi-owned captures. Leaving Find while jogging
requests Stop. Backend motion safeguards remain in force; software Stop
is not a substitute for physical Cancel/power.

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

## Next agreed task: offline VirtualSky in Find

The first UI migration step is complete. Next implement the **locally
packaged VirtualSky** planetarium inside the existing Find tab (not a
separate `/atlas` route). It is a **schematic pointing aid**, not a gallery:
no photographic sky tiles, Internet lookup or CDN.

Initial scope: permanent site, trustworthy Pi UTC with visible NTP status,
pan/zoom, stars/planets, constellation lines/labels, horizon/cardinals,
optional sky grids and all **110 Messier objects**. Clicking and simple
M-number search should centre/select a target and show its **name,
RA and Dec**, but **must not move the mount**. Full NGC/IC/OpenNGC search,
mount marker, alignment, GoTo and focusing aids come later.

Implementation stages, test criteria and source ownership are in
[DEVELOPMENT.md](DEVELOPMENT.md). Selected long-term scope is in
[REQUIREMENTS.md](REQUIREMENTS.md).

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
