# AstroPi setup and operation

## Hardware/permissions

Pi: Raspberry Pi 4B 4 GB, Debian 13 Trixie ARM64; `arn@astropi`.
The SVBONY SDK must already be installed at
`/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so`
(or set `ASTROPI_SVB_SDK`).
Camera USB is `f266:9a0a`; mount USB `03c3:4001` with stable
`/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00` (9600 8N1).
The user is in `dialout`; SVBONY camera permissions use
`/etc/udev/rules.d/90-ckusb.rules` on this trusted Pi.

Recording USB ext4 must be mounted at `/media/astropi-data` with UUID
`25b33cfa-b178-4b86-8a15-d00c8305cca5` (label `astropi-data`).
Camera recording **fails closed** if it is missing/wrong/unwritable.
No fallback to microSD.

## Launch/update (on Pi)

Stop existing Flask using Ctrl+C while mount is stationary and not saving.

```bash
cd ~/astropi
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python run.py --host 0.0.0.0 --port 8080
```

Open `http://astropi.local:8080/` or `http://<Pi-current-Wi-Fi-IP>:8080/`;
hard-refresh (Ctrl+Shift+R) after an update. The last observed
USB Wi-Fi DHCP address was `192.168.0.98`, but **it is not static**.
Flask currently runs in the foreground; **no automatic startup service is
installed**. No camera or mount serial session starts merely by loading
the page. Internet exposure/authentication is not supported.

**Three-tab browser UI: Focus / Find / Fotograph.**
Fotograph is selected initially and retains imaging/capture controls;
Focus shares the same preview and camera settings; Find contains the
offline VirtualSky chart with all 110 Messier objects (**no GoTo**).
The persistent **Mount Controls** button in the sticky status strip
opens/closes the **right-side overlay drawer** with the existing AM3N
Connect/Disconnect, speeds, directional jog, telemetry and clock/site
controls in **every tab**. It does not resize the workspace. The drawer
stays open during tab changes. Close using **Close ✕**, the top-bar
toggle or **Escape**. Closing it or switching tabs **while jogging**
requests Stop; an idle transition does not. A closed drawer cannot
begin a jog. The top-bar **STOP MOUNT** always remains available to
viewers, including when the drawer is open.
The operator token and Pi-owned exposures persist across tabs.
The original three-tab shell was Pi-checked on 2026-10-28; **the drawer
still needs a real-Pi browser check**.

## Field network — BrosTrend AC5L USB Wi-Fi

**Normal connection:** USB AC5L external-antenna adapter
(Realtek `0bda:c811`, driver `rtw88_8821cu`, Pi kernel
`6.18.39+rpt-rpi-v8`). It was detected automatically without
vendor driver installation and tested on the Pi with SSH and AstroPi
preview over multiple reboots. The saved NetworkManager profile is
`Bazingas-Minions-USB`, MAC-bound to `74:19:f8:17:b1:f5`,
`connection.autoconnect=yes`, priority **50**, route metric **100**.
The old onboard profile `Bazingas-Minions` remains in NetworkManager
as fallback, priority **0**, route metric **600**. The last observed
USB adapter IP was **192.168.0.98** (DHCP, may change).

At the last verified post-reboot network inspection, both radios
were connected and **USB Wi-Fi was preferred**. The operator
subsequently requested **disabling the onboard Wi-Fi radio at boot**;
instructions were given, but a confirming reboot report was *not*
received. Do **not** assume it is disabled until checking. The
boot setting belongs to the Pi, not Git:

```ini
# In /boot/firmware/config.txt under [all]
dtoverlay=disable-wifi
```

To verify the field network after a restart:

```bash
iw dev
nmcli device status
nmcli connection show "Bazingas-Minions-USB" | grep -E 'connection.autoconnect:|connection.interface-name:|802-11-wireless.mac-address:'
ip route
lsusb -t
grep -n '^dtoverlay=disable-wifi$' /boot/firmware/config.txt
```

Expected if the overlay was applied: only **one** wireless interface
(the AC5L), connected via `Bazingas-Minions-USB`, with the
`rtw88_8821cu` USB driver and preferred route. **It might be named
`wlan0`, not `wlan1`**, after the internal radio disappears.
Do not bind the USB connection to a device-name string; its MAC
binding is intentional. Avoid `nmcli radio wifi off` because it
disables *all* Wi-Fi adapters.

**Recovery if USB Wi-Fi stops working:** connect through Ethernet
to the Pi (for example via a LAN port providing DHCP), open a shell
and remove *only* the exact onboard-disable line, then reboot:

```bash
sudo sed -i '/^dtoverlay=disable-wifi$/d' /boot/firmware/config.txt
sudo reboot
```

This should restore the built-in radio and its existing NetworkManager
profile. A backup was prescribed at
`/boot/firmware/config.txt.before-wifi-disable`, but its presence
has not been rechecked. Do not replace the entire boot file unless
necessary. **No Wi-Fi password or boot firmware settings are stored
in this repository.**

### Known preview behaviour

Occasional ~0.5–1 s preview freezes over Wi-Fi were isolated to
the wireless/network delivery path: direct Pi-to-Mint Ethernet
made preview silky smooth without changing AstroPi code. With
the AC5L, signal improved from ~−59 dBm onboard to as strong as
~−44 dBm, and stutters seemed less frequent but **did not disappear**.
The Mint n100 still had its internal Wi-Fi; a **second AC5L has been
ordered for Mint**, not installed/tested as of this handoff. Its
future results should not be assumed. Permanent Ethernet is *not*
wanted at the telescope. For now, brief focusing-preview pauses
are acceptable; no more performance work is planned.

Pi SDK acquisition, science RAW/FITS capture and USB writes are
independent of browser JPEG timing; the actual saving of science
exposures during these network stalls was not separately verified.
A laggy Wi-Fi connection can also delay mount jog commands: retain
the mount's backend 600 ms deadman and physical hand-controller
Cancel/power fallback. Previous temporary browser/server timing
probes were removed; no special launch flags are needed.

## Camera, recording and verification

Click **Take Control**, **Start preview**, choose exposure/gain and wait for
SDK readbacks. Gain buttons select **0, 50, 100, 260, 350, 450, 550, 650**;
these are operator-requested presets (not SDK-capability-queried limits).
**Binning** buttons just below Gain select 1×1 (full sensor
3856×2180) or 2×2 (1928×1090). Binning can be changed when stopped or
running: while running, the Pi first stops and closes the existing camera
SDK session, then opens a fresh session with the new binning. Changing binning
is blocked while a capture or sequence is waiting/saving; any in-progress
exposure may delay a change until the SDK read completes. The camera may
briefly show Reconfiguring. Preview can use colour or mono, fixed or auto
display stretch. 2×2 acquisition and FITS display have passed a first
real-Pi test. **Both binning modes support Debayer On (colour) and Off
(monochrome)** for preview and JPG/PNG quicklooks. The operator verified
correct 2×2 preview colours on the real SV705C on 2026-10-28, using
AstroPi's GRBG rendering. JPG/PNG quicklooks use the same Bayer
interpretation. Scientific RAW16 and FITS keep the original binned numeric
samples, regardless of Debayer position. The 2×2 FITS currently omits
`BAYERPAT` because the writer has not yet been updated. Metadata records binning,
quicklook dimensions and whether debayering was enabled at capture start.
Select RAW16/FITS/JPG/PNG via the four format switches (FITS/JPG default),
then press **1, 5, 50, 100, 150 or 200** to save that many frames. The **1**
button saves a single exposure; all other choices start an independently
managed Pi sequence. **Cancel** stops the active multi-frame sequence after
finishing any in-progress write. No user-entered sequence count is needed. Exposure/gain, saved quicklook
stretch and saved Debayer mode are frozen for each sequence, independent
of subsequent preview toggles.

Saved captures: `/media/astropi-data/captures/<timestamp-id>/`. Each
contains the selected formats and `metadata.json` with file hashes,
sizes, timestamps and sequence indices where applicable. Files are published
atomically from `.partial` directories; USB UUID checked again at save time.
The SDK uses **one continuous stream**, and only takes a new sequence frame
after the previous disk write. Sequences continue if the browser closes,
**not** across Python process death or Pi reboot. Long exposure Stop can wait
for the current camera read to return. The FITS start-time is estimated,
not a hardware exposure timestamp.

Read-only integrity check on a capture with FITS and RAW16:

```bash
python -m astropi.capture.verify   /media/astropi-data/captures/<capture-folder>
```

## AM3N manual movement and NTP clock

Power the mount, click **Take Control**, open **Mount Controls** from
any tab, then click **Connect Mount**. Connection initializes the serial
session, verifies model/firmware and checks `timedatectl` NTP status.
If synchronized, Pi sends UTC offset `+00:00`, current UTC date/time,
requires ACKs, then checks mount readbacks against Pi UTC. UI says
**Pi NTP → mount clock: VERIFIED** only after success. The stored site is
read and displayed, **not automatically overwritten**. The mount's displayed
**Mount time (UTC)** is intentionally not local Ontario time.
If NTP is unavailable, clock remains unverified; reconnect after Pi sync.

Choose a mount speed **Slow 8×, Medium 20×, Fast 60×, Slew 720× or Max
1440×**; hold N/S/E/W immediately to move and **release to Stop**. No separate
arm and no fixed time limit. Browser focus loss or missing valid heartbeat for
600 ms requests Stop; the big Stop button is also available to viewers.
New direction cannot start until stop/settling verification completes.
Do not deliberately unplug USB while motors are moving; serial loss can defeat
software Stop. Use the physical hand-controller Cancel/power if necessary.
**No astronomical GoTo, tracking, Home or Park button exists.**

The on-demand **Refresh Clock / Site** button shows date, time, UTC
offset, sidereal time, and persistent site latitude/longitude (west-positive
in the mount protocol). The operator confirms the stored site is the
**permanent observing location: +45.2933° N, −75.8571° east-positive**.
The offline atlas uses this site and Pi UTC time already
returned by `/api/status`, without an atlas NTP test or clock-accuracy
warning. This is a deliberate permanent scope decision; it does not
affect the AM3N's existing Connect-time NTP verification. The atlas
must not modify the mount's site. AstroPi still treats reported
RA/Dec as unaligned.

## Offline Find atlas field check

Update and restart AstroPi as above, then open **Find** and confirm the
chart loads without an Internet connection. The initial view is a
north/east/south/west horizon map from **45.2933° N, 75.8571° W**.
Search `M1`, `M31`, `M42`, `M110` (or click a Messier marker) to
centre the object in detail view, show name/RA/Dec and zoom using +/−
or mouse wheel. **Horizon view** resets to the all-sky projection.
Try Constellations and RA/Dec grid toggles. Verify Pi UTC advances
without a mount connection, and no external network requests occur.
Do not interpret a chart selection as a mount GoTo. Verify camera
preview and global viewer Stop still work; leaving Find during
manual jogging must request Stop.

**Vendor note:** `astropi/static/vendor/virtualsky/PROVENANCE.md`
records source, version and upstream educational/non-profit terms.
VirtualSky is not under an explicit SPDX licence in the upstream
repository. This software is packaged for a private observatory;
review rights before redistribution or commercial use.

## Diagnostics

```bash
timedatectl show -p NTPSynchronized --value
date -u
lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS
curl -s http://127.0.0.1:8080/api/mount/status | python3 -m json.tool
curl -s http://127.0.0.1:8080/api/status | python3 -m json.tool
```

If manual movement or NTP verification fails, capture the UI error and the
read-only mount status **after the mount has stopped**. Do not open the same
USB serial port in a second diagnostic process while AstroPi owns it.
Optional on a development machine with Node.js 22+:
`node --test tests/test_ui.cjs tests/test_atlas.cjs`. Node is **not** required to run
AstroPi on the Pi; GitHub CI also runs these browser regression tests.
For architecture and verified hardware quirks see [DEVELOPMENT.md](DEVELOPMENT.md)
and [HARDWARE.md](HARDWARE.md).
