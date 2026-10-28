"use strict";

const exposurePresets = [1000,2000,5000,10000,25000,50000,100000,250000,500000,750000,1000000,2000000,5000000,10000000,15000000,20000000,25000000,30000000];
const gainPresets = [0,50,100,260,350,450,550,650];
let token = null;
let currentPhase = "stopped";
let desiredGain = 0;
let desiredExposureUs = 100000;
let settingsInitialized = false;
let sendBusy = false;
let staged = false;
let pendingSettingsId = null;
let stretchChangePending = false;
let debayerChangePending = false;
let binningChangePending = false;
let selectedBinning = 1;
let previousFrame = -1;
const workspaceTabs = ["focus", "find", "fotograph"];
let activeTab = "fotograph";
let progressBusy = false;
let storageReady = false;
let captureBusy = false;
let captureRequestPending = false;
let sequenceActive = false;
let mountPhase = "disconnected";
let mountRequestPending = false;
let mountMotionPhase = "idle";
let heldMountDirection = null;
let mountStopPending = false;
let mountHeartbeatBusy = false;
let mountEnvironmentPhase = "idle";
const mountSpeeds = ["slow", "medium", "fast", "slew", "max"];
let selectedMountSpeed = "slow";
function showMountSpeed(speed) {
  selectedMountSpeed = speed;
  for (const option of mountSpeeds)
    $("mount-speed-" + option).checked = option === speed;
}
const saveFormats = ["fits", "raw", "jpg", "png"];
const captureCounts = [1, 5, 50, 100, 150, 200];
const $ = id => document.getElementById(id);
const write = (id, value) => { $(id).textContent = value; };
const nearest = (values, number) => values.reduce((a, b) =>
  Math.abs(a - number) <= Math.abs(b - number) ? a : b);
function formatExposure(us) {
  return us >= 1000000 ? (us / 1000000).toFixed(3) + " s" : (us / 1000).toFixed(3) + " ms";
}
function freeSpace(bytes) {
  return typeof bytes === "number" ? (bytes / 1024 ** 3).toFixed(1) + " GiB free" : "Free space unavailable";
}
function renderSelections() {
  for (const v of exposurePresets) $("exposure-" + v).checked = v === desiredExposureUs;
  for (const v of gainPresets) $("gain-" + v).checked = v === desiredGain;
  for (const bin of [1, 2]) $("binning-" + bin).checked = bin === selectedBinning;
}
function toggleView(prefix, first, second, activeFirst) {
  const a = $(prefix + "-" + first), b = $(prefix + "-" + second);
  a.className = "stretch-choice" + (activeFirst ? " selected" : "");
  b.className = "stretch-choice" + (!activeFirst ? " selected" : "");
  a.setAttribute("aria-pressed", String(activeFirst));
  b.setAttribute("aria-pressed", String(!activeFirst));
  $(prefix + "-indicator").className = "stretch-indicator " + (activeFirst ? "auto" : "fixed");
}
function showStretch(mode) { toggleView("stretch", "auto", "fixed", mode !== "fixed"); }
function showDebayer(enabled) { toggleView("debayer", "on", "off", enabled); }
function updateButtons() {
  const owner = Boolean(token);
  $("take-control").hidden = owner;
  $("release-control").hidden = !owner;
  $("start-camera").disabled = !owner || !["stopped", "error"].includes(currentPhase);
  $("stop-camera").disabled = !owner || !["running", "connecting"].includes(currentPhase);
  $("mount-connect").disabled = !owner || mountRequestPending ||
    !["disconnected", "error"].includes(mountPhase);
  $("mount-disconnect").disabled = !owner || mountRequestPending ||
    !["connecting", "connected"].includes(mountPhase);
  $("mount-stop").disabled = mountPhase !== "connected" || mountStopPending;
  $("mount-read-environment").disabled = !owner || mountPhase !== "connected" ||
    mountRequestPending || mountMotionPhase !== "idle" || Boolean(heldMountDirection) ||
    mountEnvironmentPhase === "queued" || mountEnvironmentPhase === "reading";
  for (const speed of mountSpeeds) {
    $("mount-speed-" + speed).disabled = !owner || mountPhase !== "connected" ||
      mountMotionPhase !== "idle" || mountRequestPending ||
      Boolean(heldMountDirection);
  }
  for (const direction of ["north", "south", "east", "west"]) {
    $("mount-" + direction).disabled = !owner || mountPhase !== "connected" ||
      (mountMotionPhase !== "idle" && heldMountDirection !== direction) ||
      (Boolean(heldMountDirection) && heldMountDirection !== direction) ||
      activeTab !== "find" || mountRequestPending ||
      ["queued", "reading"].includes(mountEnvironmentPhase);
  }
  const saveReady = owner && currentPhase === "running" &&
    storageReady && !captureBusy && !captureRequestPending &&
    saveFormats.some(fmt => $("capture-" + fmt).checked);
  for (const count of captureCounts)
    $("capture-" + count).disabled = !saveReady;
  for (const fmt of saveFormats)
    $("capture-" + fmt).disabled = !owner || captureBusy || captureRequestPending;
  $("cancel-sequence").disabled = !owner || !sequenceActive;
  for (const bin of [1, 2])
    $("binning-" + bin).disabled = !owner || binningChangePending ||
      !["stopped", "error", "running"].includes(currentPhase) ||
      captureBusy || captureRequestPending || sendBusy || staged ||
      pendingSettingsId !== null;

  const active = owner && currentPhase === "running";
  for (const v of exposurePresets) $("exposure-" + v).disabled = !active || sequenceActive;
  for (const v of gainPresets) $("gain-" + v).disabled = !active || sequenceActive;
  for (const id of ["stretch-auto", "stretch-fixed"])
    $(id).disabled = !owner || stretchChangePending;
  for (const id of ["debayer-on", "debayer-off"])
    $(id).disabled = !owner || debayerChangePending;
}
function syncSettings(data) {
  // SDK readbacks may be rounded; map to the closest visible radio option.
  if (!settingsInitialized) {
    desiredGain = nearest(gainPresets, data.gain);
    desiredExposureUs = nearest(exposurePresets, data.exposure_us);
    settingsInitialized = true;
  }
  if (pendingSettingsId !== null && !sendBusy && !staged &&
      data.settings_applied_id >= pendingSettingsId) {
    pendingSettingsId = null;
    write("settings-message", "Camera settings applied");
  }
  // Never overwrite an optimistic radio selection while the request is in
  // flight or queued: it can take ~30 s to finish an exposure.
  if (pendingSettingsId === null && !sendBusy && !staged) {
    desiredGain = nearest(gainPresets, data.gain);
    desiredExposureUs = nearest(exposurePresets, data.exposure_us);
  }
  renderSelections();
  write("exposure-readback", "Actual exposure: " + formatExposure(data.exposure_us));
  write("gain-readback", "Actual gain: " + data.gain);
  if (data.phase === "error" && pendingSettingsId !== null) {
    pendingSettingsId = null;
    write("settings-message", "Camera stopped before applying changes");
  }
}
async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", ...(token ? {"X-AstroPi-Control": token} : {})},
    body: JSON.stringify(payload || {})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
  return data;
}
async function action(path) {
  try {
    await post(path);
    write("camera-error", "");
    await refresh();
  } catch (error) {
    write("camera-error", error.message);
  }
}
// Automatically send a complete exposure+gain pair with EACH radio change.
// In-flight HTTP requests serialize; rapid clicks are coalesced to newest choice.
async function applySelected() {
  if (!token || currentPhase !== "running") return;
  if (sendBusy) { staged = true; return; }
  sendBusy = true;
  try {
    do {
      staged = false;
      const gain = desiredGain, exposure_us = desiredExposureUs;
      const reply = await post("/api/camera/settings", {gain, exposure_us});
      pendingSettingsId = reply.request_id;
      write("settings-message", "Applying exposure " + formatExposure(exposure_us) +
        ", gain " + gain + "…");
    } while (staged && token && currentPhase === "running");
    write("camera-error", "");
  } catch (error) {
    write("camera-error", error.message);
    pendingSettingsId = null;
    settingsInitialized = false;
    staged = false;
  } finally {
    sendBusy = false;
    updateButtons();
  }
}
for (const value of exposurePresets) {
  $("exposure-" + value).addEventListener("change", () => {
    desiredExposureUs = value;
    renderSelections();
    return applySelected();
  });
}
for (const value of gainPresets) {
  $("gain-" + value).addEventListener("change", () => {
    desiredGain = value;
    renderSelections();
    return applySelected();
  });
}
async function changeBinning(binning) {
  if (!token || binningChangePending || captureBusy || captureRequestPending) return;
  binningChangePending = true;
  updateButtons();
  write("binning-message", "Reconfiguring camera for " + binning + "×" + binning + "…");
  try {
    await post("/api/camera/binning", {binning});
    selectedBinning = binning;
    write("binning-message", "Binning " + binning + "×" + binning +
      " selected · camera reopens if it was running");
    write("camera-error", "");
  } catch (error) {
    write("camera-error", error.message);
    write("binning-message", "Binning unchanged");
  } finally {
    binningChangePending = false;
    renderSelections();
    updateButtons();
    await refresh();
  }
}
for (const bin of [1, 2]) {
  $("binning-" + bin).addEventListener("change", () => changeBinning(bin));
}
$("take-control").addEventListener("click", async () => {
  try {
    token = (await post("/api/control/take")).token;
    write("camera-error", "");
  } catch (error) { write("camera-error", error.message); }
  updateButtons();
});
$("release-control").addEventListener("click", async () => {
  try {
    await post("/api/control/release");
    token = null;
    pendingSettingsId = null;
    staged = false;
    settingsInitialized = false;
    await refresh();
  } catch (error) { write("camera-error", error.message); }
  updateButtons();
});
for (const speed of mountSpeeds) {
  $("mount-speed-" + speed).addEventListener("change", () => {
    if (mountMotionPhase !== "idle" || heldMountDirection) {
      showMountSpeed(selectedMountSpeed);
      return;
    }
    showMountSpeed(speed);
    updateButtons();
  });
}
// Pointer holds have no click-to-latch behaviour. The *Pi* enforces the 600ms
// deadline; browser events are an additional first line of defence.
// Switching views must never leave a manual jog running.
function activateTab(name, focusTab=false) {
  if (!workspaceTabs.includes(name)) return;
  if (activeTab === "find" && name !== "find" &&
      (heldMountDirection || ["starting", "moving"].includes(mountMotionPhase)))
    stopMount();
  activeTab = name;
  for (const tab of workspaceTabs) {
    const selected = tab === name;
    const button = $("tab-" + tab);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $("panel-" + tab).hidden = !selected;
  }
  if (name !== "find") {
    // Relocate the same preview and settings DOM; no duplicate camera stream.
    $(name + "-preview-slot").appendChild($("shared-preview-card"));
    $(name + "-controls-slot").appendChild($("shared-camera-controls"));
  }
  if (name === "find") window.AstroPiAtlas?.show();
  else window.AstroPiAtlas?.hide();
  if (focusTab) $("tab-" + name).focus();
  updateButtons();
}
for (const tab of workspaceTabs) {
  $("tab-" + tab).addEventListener("click", () => activateTab(tab));
  $("tab-" + tab).addEventListener("keydown", event => {
    const i = workspaceTabs.indexOf(tab);
    const target = event.key === "ArrowRight" ? workspaceTabs[(i+1)%3] :
      event.key === "ArrowLeft" ? workspaceTabs[(i+2)%3] :
      event.key === "Home" ? workspaceTabs[0] :
      event.key === "End" ? workspaceTabs[2] : null;
    if (target) { event.preventDefault(); activateTab(target, true); }
  });
}
activateTab("fotograph");

async function stopMount() {
  heldMountDirection = null;
  if (mountStopPending || mountPhase !== "connected") return;
  mountStopPending = true;
  // Lock out speed changes immediately, before the serial owner has
  // acknowledged and verified a complete Stop.
  mountMotionPhase = "stopping";
  updateButtons();
  try {
    await post("/api/mount/stop");
    write("mount-motion", "Stop requested · checking axes for stability…");
    write("mount-error", "");
  } catch(error) {
    const warning = "Stop request failed: " + error.message +
      " · USE PHYSICAL CANCEL/POWER!";
    write("mount-error", warning);
    write("global-mount-alert", warning);
  } finally {
    mountStopPending = false;
    updateButtons();
  }
}
$("mount-stop").addEventListener("click", stopMount);
async function beginMountHold(direction) {
  if (activeTab !== "find" || heldMountDirection || !token || mountPhase !== "connected" ||
      mountMotionPhase !== "idle" ||
      ["queued", "reading"].includes(mountEnvironmentPhase)) return;
  heldMountDirection = direction;
  mountMotionPhase = "starting";
  updateButtons();
  try {
    await post("/api/mount/jog", {direction, speed:selectedMountSpeed});
    if (heldMountDirection !== direction) return; // Release already requested
    write("mount-motion", "Jog " + direction + " (" + selectedMountSpeed +
      ") requested · hold button");
    write("mount-error", "");
  } catch(error) {
    heldMountDirection = null;
    write("mount-error", error.message);
    await stopMount();
  }
}
for (const direction of ["north", "south", "east", "west"]) {
  const button = $("mount-" + direction);
  button.addEventListener("pointerdown", () => beginMountHold(direction));
  for (const kind of ["pointerup", "pointercancel", "pointerleave"]) {
    button.addEventListener(kind, () => {
      if (heldMountDirection === direction) stopMount();
    });
  }
}
document.addEventListener("pointerup", () => {
  if (heldMountDirection) stopMount();
});
document.addEventListener("pointercancel", () => {
  if (heldMountDirection) stopMount();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && heldMountDirection) stopMount();
});
window.addEventListener("blur", () => {
  if (heldMountDirection) stopMount();
});
window.addEventListener("pagehide", () => {
  if (heldMountDirection) stopMount();
});
async function mountHoldHeartbeat() {
  const direction = heldMountDirection;
  if (!direction || mountHeartbeatBusy) return;
  mountHeartbeatBusy = true;
  try {
    await post("/api/mount/jog-heartbeat", {direction});
  } catch(error) {
    write("mount-error", "Jog heartbeat failed: " + error.message);
    await stopMount();
  } finally {
    mountHeartbeatBusy = false;
  }
}
$("mount-read-environment").addEventListener("click", async () => {
  if (!token || mountPhase !== "connected" || mountMotionPhase !== "idle" ||
      heldMountDirection || ["queued","reading"].includes(mountEnvironmentPhase)) return;
  mountEnvironmentPhase = "queued";
  updateButtons();
  try {
    await post("/api/mount/environment/read");
    write("mount-environment-error", "");
    await refreshMount();
  } catch (error) {
    mountEnvironmentPhase = "error";
    write("mount-environment-error", error.message);
  } finally {
    updateButtons();
  }
});
$("mount-connect").addEventListener("click", () => mountAction("/api/mount/connect"));
$("mount-disconnect").addEventListener("click", () => mountAction("/api/mount/disconnect"));
async function mountAction(url) {
  if (!token || mountRequestPending) return;
  mountRequestPending = true;
  updateButtons();
  try {
    await post(url);
    write("mount-error", "");
    await refreshMount();
  } catch(error) {
    write("mount-error", error.message);
  } finally {
    mountRequestPending = false;
    updateButtons();
  }
}
function describeFlag(v, whenTrue, whenFalse) {
  return v === true ? whenTrue : v === false ? whenFalse : "unknown";
}
function showMount(data) {
  if (!data) return;
  const nextPhase = data.phase || "disconnected";
  if (mountPhase !== "connected" && nextPhase === "connected")
    showMountSpeed("slow");  // reconnect always starts conservatively
  mountPhase = nextPhase;
  write("global-mount-state", "Mount: " + mountPhase);
  mountMotionPhase = data.motion_phase || "idle";
  mountEnvironmentPhase = data.environment_phase || "idle";
  const syncPhase = data.time_sync_phase || "idle";
  const syncLabels = {
    idle: "Pi NTP → mount clock: not synchronized",
    checking: "Pi NTP → mount clock: checking NTP synchronization…",
    syncing: "Pi NTP → mount clock: setting UTC and verifying…",
    verified: "Pi NTP → mount clock: VERIFIED" +
      (data.time_sync_verified_utc ? " (" +
        new Date(data.time_sync_verified_utc).toLocaleTimeString() + ")" : ""),
    error: "Pi NTP → mount clock: NOT synchronized"
  };
  write("mount-time-sync", syncLabels[syncPhase] || ("Clock sync: " + syncPhase));
  write("mount-time-sync-error", data.time_sync_error || "");
  if (mountPhase !== "connected") heldMountDirection = null;
  const env = mountPhase === "connected" ? data.environment : null;
  write("mount-environment-state", env ?
    "Clock/site snapshot: " + (data.environment_updated_utc || "received") :
    "Clock/site: " + mountEnvironmentPhase);
  const fields = {
    "mount-env-date": "date",
    "mount-env-time": "local_time",
    "mount-env-offset": "utc_offset",
    "mount-env-sidereal": "sidereal_time",
    "mount-env-latitude": "latitude",
    "mount-env-longitude": "longitude_west"
  };
  for (const [id, key] of Object.entries(fields))
    write(id, env && env[key] ? env[key] : "—");
  write("mount-environment-error", data.environment_error || "");
  write("mount-phase", "Connection: " + mountPhase);
  const motionDescription = {
    idle: data.stop_stable ? "Axes stable" : "Idle",
    starting: "Starting jog",
    moving: "Jog " + (data.jog_speed || "slow") + " active",
    stopping: "Stop requested · checking position stability…",
    uncertain: "STOP NOT CONFIRMED — use physical Cancel/power!",
    disconnecting: "Disconnecting (Stop attempted if necessary)"
  };
  write("mount-motion", motionDescription[mountMotionPhase] || mountMotionPhase);
  write("mount-motion-warning", data.motion_warning || "");
  write("mount-model", data.model ?
    "Model: " + data.model + " · firmware " + (data.firmware || "—") :
    "Model / firmware: —");
  const active = Boolean(data.connected && mountPhase === "connected");
  write("mount-altitude", active ? (data.altitude_text || "—") : "—");
  write("mount-azimuth", active ? (data.azimuth_text || "—") : "—");
  write("mount-ra", active ? (data.ra_text || "—") : "—");
  write("mount-dec", active ? (data.dec_text || "—") : "—");
  write("mount-flags", active ?
    "Flags: " + [
      describeFlag(data.tracking,"tracking","not tracking"),
      describeFlag(data.slewing,"slewing","not slewing"),
      describeFlag(data.at_home,"at Home","Home unknown"),
      describeFlag(data.altaz_mode,"Alt/Az","mode unknown")
    ].join(" · ") : "Status flags: —");
  write("mount-raw-status", "Raw :GU#: " + (active ? data.raw_status || "—" : "—"));
  write("mount-update", "Last telemetry: " +
    (active && data.updated_utc ? new Date(data.updated_utc).toLocaleTimeString() : "—"));
  write("mount-error", data.last_error || "");
  if (mountMotionPhase === "uncertain") {
    const warning = "Mount not confirmed stopped. USE PHYSICAL CANCEL/POWER.";
    write("mount-error", warning);
    write("global-mount-alert", warning);
  } else if (data.motion_warning || data.last_error) {
    write("global-mount-alert", data.motion_warning || data.last_error);
  } else if (mountMotionPhase === "idle" && data.stop_stable) {
    write("global-mount-alert", "");
  }
  updateButtons();
}
async function refreshMount() {
  try {
    const response = await fetch("/api/mount/status", {cache:"no-store"});
    if (!response.ok) throw new Error("Mount status unavailable");
    showMount(await response.json());
  } catch(error) {
    write("mount-error", error.message);
  }
}
$("start-camera").addEventListener("click", () => action("/api/camera/start"));
$("stop-camera").addEventListener("click", () => action("/api/camera/stop"));
async function changeStretch(mode) {
  if (!token || stretchChangePending) return;
  stretchChangePending = true;
  updateButtons();
  try {
    await post("/api/camera/preview-mode", {mode});
    showStretch(mode);
    write("camera-error", "");
  } catch (error) {
    write("camera-error", error.message);
    await refresh();
  } finally {
    stretchChangePending = false;
    updateButtons();
  }
}
$("stretch-auto").addEventListener("click", () => changeStretch("auto"));
$("stretch-fixed").addEventListener("click", () => changeStretch("fixed"));
async function changeDebayer(enabled) {
  if (!token || debayerChangePending) return;
  debayerChangePending = true;
  updateButtons();
  try {
    await post("/api/camera/debayer", {enabled});
    showDebayer(enabled);
    write("camera-error", "");
  } catch (error) {
    write("camera-error", error.message);
    await refresh();
  } finally {
    debayerChangePending = false;
    updateButtons();
  }
}
$("debayer-on").addEventListener("click", () => changeDebayer(true));
$("debayer-off").addEventListener("click", () => changeDebayer(false));

for (const fmt of saveFormats) {
  $("capture-" + fmt).addEventListener("change", updateButtons);
}
async function requestFrames(count) {
  if (!captureCounts.includes(count) || captureBusy || captureRequestPending ||
      $("capture-" + count).disabled) return;
  const formats = saveFormats.filter(fmt => $("capture-" + fmt).checked);
  if (!formats.length) {
    write("capture-error", "Select at least one file format");
    return;
  }
  captureRequestPending = true;
  updateButtons();
  write("capture-error", "");
  write("capture-results", "");
  write("sequence-progress", count > 1 ? "Starting " + count + " frames…" : "");
  write("capture-state", count > 1 ? "Starting sequence…" : "Requesting next frame…");
  try {
    if (count === 1) {
      const reply = await post("/api/capture", {formats});
      write("capture-state", "Capture " + reply.id + " queued");
    } else {
      const reply = await post("/api/capture/sequence", {count, formats});
      write("capture-state", "Sequence " + reply.id + " accepted");
      write("sequence-progress", "0 / " + count + " frames saved");
    }
  } catch (error) {
    write("capture-error", error.message);
    write("capture-state", "Capture not started");
    write("sequence-progress", "");
  } finally {
    captureRequestPending = false;
    updateButtons();
  }
}
for (const count of captureCounts)
  $("capture-" + count).addEventListener("click", () => requestFrames(count));
$("cancel-sequence").addEventListener("click", async () => {
  if (!sequenceActive || $("cancel-sequence").disabled) return;
  $("cancel-sequence").disabled = true;
  try {
    await post("/api/capture/cancel");
    write("capture-state", "Cancellation requested; completing active write…");
    write("capture-error", "");
    sequenceActive = false;
    updateButtons();
  } catch (error) {
    write("capture-error", error.message);
    updateButtons();
  }
});
function showCapture(job) {
  if (!job) return;
  captureBusy = job.phase === "waiting" || job.phase === "saving";
  sequenceActive = captureBusy && job.total_frames > 1 && !job.cancel_requested;
  const total = Number(job.total_frames || 0);
  const completed = Number(job.completed_frames || 0);
  const stages = {idle: "No capture requested", waiting: "Waiting for next camera frame…",
    saving: "Saving files on USB drive…", done: "Capture saved to USB drive",
    cancelled: "Capture sequence cancelled", error: "Capture failed"};
  write("capture-state", (total > 1 ? "Sequence: " : "") +
    (stages[job.phase] || job.phase));
  write("global-capture-state", total > 1 && captureBusy ?
    "Capture: " + completed + "/" + total : "Capture: " + (job.phase || "idle"));
  write("sequence-progress", total > 1 ? completed + " / " + total +
    " frames saved" + (job.cancel_requested ? " · stopping after current write" : "") :
    "");
  if (job.phase === "error" && job.error) write("capture-error", job.error);
  if (["done", "cancelled", "error"].includes(job.phase)) {
    if (job.phase === "done") write("capture-error", "");
    if (total > 1 && Array.isArray(job.directories)) {
      write("capture-results", job.directories.length + " completed frame folders:\n" +
        job.directories.join("\n"));
    } else if (Array.isArray(job.files) && job.files.length) {
      const lines = ["Saved: " + job.directory, "metadata.json (settings and checksums)",
        ...job.files.map(file => file.format + ": " + file.path +
          " (" + (file.bytes / 1048576).toFixed(1) + " MiB)")];
      write("capture-results", lines.join("\n"));
    }
  }
  updateButtons();
}
function showProgress(data) {
  currentPhase = data.phase;
  if (!binningChangePending && [1, 2].includes(data.binning)) {
    selectedBinning = data.binning;
    renderSelections();
  }
  if ([1, 2].includes(data.binning)) {
    write("binning-readback", "Binning: " + data.binning + "×" +
      data.binning + " · " + (data.width || 3856) + "×" +
      (data.height || 2180));
  }
  if (data.phase === "reconfiguring")
    write("binning-message", "Reopening camera with selected binning…");
  if (data.capture) showCapture(data.capture);
  write("camera-phase", "Camera: " + data.phase);
  write("global-camera-state", "Camera: " + data.phase);
  const fps = typeof data.preview_fps === "number" ? data.preview_fps.toFixed(1) + " fps" : "— fps";
  const raw = typeof data.capture_fps === "number" ? data.capture_fps.toFixed(1) + " fps" : "— fps";
  const processing = typeof data.preview_processing_ms === "number" ? data.preview_processing_ms.toFixed(0) + " ms" : "— ms";
  write("frame-count", (data.frame_number || 0) + " JPEG frames · " + fps +
    " preview · " + raw + " raw · " + processing + " processing");
  if (typeof data.exposure_us === "number" && typeof data.gain === "number" &&
      typeof data.settings_applied_id === "number") syncSettings(data);
  if (!stretchChangePending && ["auto", "fixed"].includes(data.preview_mode))
    showStretch(data.preview_mode);
  if (!debayerChangePending && typeof data.debayer === "boolean")
    showDebayer(data.debayer);
  if (typeof data.raw_mean_adu === "number") {
    write("raw-metrics", "RAW mean: " + data.raw_mean_adu.toFixed(1) +
      " / 4095 ADU · 99th percentile: " + data.raw_p99_adu +
      " · saturated: " + data.raw_saturated_percent.toFixed(2) + "%");
  } else write("raw-metrics", "Raw sensor signal: waiting for frames…");
  updateButtons();
  const img = $("preview-image");
  if (!data.has_frame) {
    img.hidden = true;
    $("preview-placeholder").hidden = false;
    previousFrame = -1;
  } else if (data.frame_number !== previousFrame) {
    previousFrame = data.frame_number;
    img.src = "/api/camera/frame.jpg?frame=" + data.frame_number + "&t=" + Date.now();
    img.hidden = false;
    $("preview-placeholder").hidden = true;
  }
}
async function refresh() {
  const el = $("connection");
  try {
    const response = await fetch("/api/status", {cache:"no-store"});
    if (!response.ok) throw Error("HTTP " + response.status);
    const data = await response.json();
    window.AstroPiAtlas?.syncUTC(data.utc);
    el.textContent = token ? "Connected · Controller" : "Connected · Viewer";
    el.className = "connection online";
    write("camera-usb", data.camera.usb_detected ? "Camera USB detected" : "Camera USB not detected");
    if (data.camera.last_error) write("camera-error", data.camera.last_error);
    write("mount-usb", data.mount.usb_detected ? "USB detected" : "USB not detected");
    write("mount-serial", data.mount.serial_present ? "Serial alias available" : "Serial alias unavailable");
    showMount(data.mount);
    storageReady = Boolean(data.storage.ready);
    write("storage-state", data.storage.ready ? "Recording drive ready" : data.storage.state.replaceAll("_", " "));
    write("storage-free", freeSpace(data.storage.free_bytes));
    write("pi-temp", data.host.cpu_temperature_c === null ? "Temperature unavailable" : data.host.cpu_temperature_c + " °C");
    const s = data.host.uptime_seconds;
    write("pi-uptime", typeof s === "number" ? "Uptime: " + Math.floor(s / 86400) +
      "d " + Math.floor(s % 86400 / 3600) + "h" : "Uptime unavailable");
    write("last-update", new Date(data.utc).toLocaleTimeString());
    showProgress({...data.camera, capture:data.capture});
  } catch (error) {
    el.textContent = "Service unavailable";
    el.className = "connection offline";
  }
}
async function pollPreview() {
  if (progressBusy || !["connecting", "running", "stopping", "reconfiguring"].includes(currentPhase)) return;
  progressBusy = true;
  try {
    const response = await fetch("/api/camera/progress", {cache:"no-store"});
    if (response.ok) {
      const data = await response.json();
      if (data.last_error) write("camera-error", data.last_error);
      showProgress(data);
    }
  } catch {
    // Full status poll will report backend connection failures.
  } finally { progressBusy = false; }
}
async function heartbeat() {
  if (!token) return;
  try { await post("/api/control/heartbeat"); }
  catch {
    token = null;
    pendingSettingsId = null;
    staged = false;
    updateButtons();
  }
}
refresh();
setInterval(refresh, 3000);
setInterval(refreshMount, 1000);
setInterval(mountHoldHeartbeat, 150);
setInterval(pollPreview, 50);
setInterval(heartbeat, 5000);
