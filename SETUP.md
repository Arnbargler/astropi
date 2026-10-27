# AstroPi — v0.2 experimental SV705C browser preview

Hardware v0.1 read-only status checks passed in the browser on 2026-10-27. This update integrates the existing SVBONY SDK into a single-thread worker to show a browser JPEG preview and set exposure/gain. **SDK camera integration has not yet been verified on the Pi**. No RAW/FITS saving, mount movement or telescope tracking is implemented.

Run on AstroPi (while physically present or able to monitor its terminal):

    cd ~/astropi
    # Stop the old Flask service first (Ctrl+C in its terminal).
    git pull --ff-only
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    python run.py --host 0.0.0.0 --port 8080

From the trusted LAN, open http://192.168.0.29:8080/ or http://astropi.local:8080/. Select **Take Control**, then **Start preview**. The camera worker opens the SV705C once, uses full 3856x2180 RAW16 frames from the SDK and sends a reduced ~964x545 8-bit colour JPEG to the page. It never saves those buffers. Change gain and exposure in the browser, then use **Apply settings**. Multiple browsers can see the same preview, but only one control lease can change settings.

Use **Stop** before Ctrl+C or before changing devices. Normal Stop may finish an in-progress exposure before closing the SDK. If restart fails, report the on-screen SDK error and Pi terminal output; previous hardware probes observed SDK error 11 on some stream restarts. This release does not attempt blind automatic resets. The Flask server is still a temporary development server without auto-start; do not forward the port to the Internet.

Preview is display-only: percentile stretch and simple 4x4 GRBG block averaging, not a calibrated demosaic. The original 12-bit-in-RAW16 data is not modified, but no science FITS output is implemented yet. Do not infer exact exposure calibration from SDK readback.

When using the dark lens cap, expect a mostly dark preview. Try the previously tested Canon lens under indoor lighting, starting around **100 ms exposure, gain 0**, rather than pointing the bare sensor at bright sunlight.

If tests fail, do not start the new service; copy the failing traceback. Hardware SDK bindings are based on the project's tested v1.13.4 integration notes and still need first live verification.

## 2026-10-27 SDK control-order correction

The first integrated SV705C browser test encountered SDK error code 16 from SVBSetControlValue before a preview appeared. The follow-up commit sets exposure before gain (a published SVBONY workaround) and makes control-setting errors identify which control/value failed. This is an unverified hypothesis until retested on AstroPi, not a confirmed root cause. The mock unit test checks order, not actual camera behavior.

Stop Flask using Ctrl+C, pull changes, run pytest, restart, and attempt Take Control -> Start preview. If a new error occurs, report its exact message. Do not repeatedly unplug or reset equipment.

## Preview responsiveness and input-draft fix (2026-10-27)

The SV705C live colour preview was confirmed working on AstroPi. Two UI/performance bugs were found: the three-second polling cycle replaced unsaved exposure/gain inputs after focus moved, and the browser's 1200ms image timer plus 750ms backend frame throttle prevented a fast preview. This update independently preserves dirty values until **Apply settings**, acknowledges a settings command only when the single SDK worker has applied it, and checks for new camera frames at 200ms intervals (downloading the JPEG only when its sequence number changes). Backend preview cap is now 250ms and it reports **measured JPEG preview FPS**, **measured camera read FPS**, and **JPEG-processing milliseconds**. There is no promise of a particular frame rate: full-frame RAW16 exposure, USB read time and Pi CPU processing still determine it.

Stop the Flask server (Ctrl+C), pull, run `python -m pytest -q`, then restart. Refresh the browser (Ctrl+Shift+R). Try 50ms or 100ms exposure first, edit BOTH exposure and gain without pressing Apply, wait >3 seconds to verify edits remain unchanged, then click Apply once. Report the measured FPS and processing time displayed below the preview. There is no RAW/FITS recording and no mount action in this update.


## Gain visibility diagnosis — new preview controls (2026-10-27)

AstroPi's full-frame SV705C colour preview works, but changing gain was not visually obvious. The initial JPEG processing uses a different low/high percentile for **each frame and colour channel**, cancelling many brightness changes. This does **not** prove gain is ineffective: earlier separate hardware probes measured the raw mean rising about 3.3x from gain 0 to 100 at the same exposure.

The new **Preview brightness** selector has two options:
- **Auto stretch — faint detail:** current per-frame adaptive preview for astronomy. Brightness changes can be disguised.
- **Fixed stretch — compare gain:** one gamma-adjusted 0–4095 mapping for every frame. Use this for gain/exposure comparisons; the image may look darker.

The panel now displays **RAW mean / 4095 ADU**, **99th-percentile ADU** and **% saturated**, computed from a small subset of unmodified RAW16 frame pixels (12-bit values obtained with >>4). These are indicative, not sensor calibration. Use an evenly lit scene and constant exposure. Test gain 0 and gain 100, waiting for Applied and for at least two fresh JPEG frames each time. The RAW mean should change if gain is taking effect. If it does not, report the displayed mean, gain and exposure; then check the SDK control path. All adjustments are display-only except the existing explicit camera gain/exposure controls. No RAW/FITS data is saved.


## Compact Stretch toggle and exposure presets (2026-10-27)

Exposure is now a single preset drop-down (18 choices): 1, 2, 5, 10, 25, 50, 100, 250, 500, 750 ms; 1, 2, 5, 10, 15, 20, 25 and 30 seconds. It is sent to the SDK in **microseconds**; the worker still reports the quantized actual readback separately. Choose a preset and gain, then click **Apply settings**. Until then, both are drafts that must not be rewritten by polling.

The old stretch drop-down has been replaced with the compact **Stretch** A/F switch with a selected-state indicator. **A** = auto percentile stretch, **F** = fixed scale. The backend remains authoritative and only the controlling browser can change it. Stretch switches immediately; exposure/gain still require Apply.

**Important:** The previous 8000 ms SDK frame-wait cap would cause long exposures to time out. The camera worker now waits for the full requested exposure plus a 4 s transfer margin, so 30 s can block for about 34 s before a timeout. Stop is cooperative and might not finish until an in-flight exposure ends. Long exposures beyond previously verified tests are **not yet hardware-proven**, so begin at 1–2 s, then try 5–10 s before testing 30 s. No automatic mount action or RAW/FITS file recording is enabled.
