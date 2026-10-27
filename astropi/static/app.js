"use strict";
let token = null;
let currentPhase = "stopped";
let pendingSettingsId = null;
let previousFrame = -1;
let progressBusy = false;
// Track each field independently. A 3-second status poll must NEVER erase
// unsubmitted edits when the operator switches between exposure and gain.
const dirty = {"gain": false, "exposure-ms": false};
const $ = id => document.getElementById(id);
function write(id, value) { $(id).textContent = value; }
function freeSpace(bytes) {
  return typeof bytes === "number" ? (bytes / 1024 ** 3).toFixed(1) + " GiB free" : "Free space unavailable";
}
function updateButtons() {
  const owner = Boolean(token);
  $("take-control").hidden = owner;
  $("release-control").hidden = !owner;
  $("start-camera").disabled = !owner || !["stopped", "error"].includes(currentPhase);
  $("stop-camera").disabled = !owner || !["running", "connecting"].includes(currentPhase);
  const editEnabled = owner && currentPhase === "running" && pendingSettingsId === null;
  for (const id of ["gain", "exposure-ms", "apply-settings"]) {
    $(id).disabled = !editEnabled;
  }
}
for (const id of ["gain", "exposure-ms"]) {
  $(id).addEventListener("input", () => {
    dirty[id] = true;
    write("settings-message", "Unsaved changes · click Apply settings");
  });
}
function discardEdits() {
  dirty.gain = false;
  dirty["exposure-ms"] = false;
  pendingSettingsId = null;
  write("settings-message", "");
}
function syncSettings(data) {
  if (pendingSettingsId !== null) {
    if (data.settings_applied_id >= pendingSettingsId) {
      // SDK readbacks are authoritative only after its worker acknowledges the request.
      pendingSettingsId = null;
      dirty.gain = false;
      dirty["exposure-ms"] = false;
      write("settings-message", "Settings applied");
    } else if (data.phase === "error" || data.phase === "stopped") {
      pendingSettingsId = null;
      write("settings-message", "Camera stopped before settings were applied");
    }
  }
  if (!dirty.gain && pendingSettingsId === null && document.activeElement !== $("gain")) {
    $("gain").value = data.gain;
  }
  if (!dirty["exposure-ms"] && pendingSettingsId === null && document.activeElement !== $("exposure-ms")) {
    $("exposure-ms").value = Math.round(data.exposure_us / 1000);
  }
}
async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", ...(token ? {"X-AstroPi-Control": token} : {})},
    body: JSON.stringify(payload || {})
  });
  const output = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(output.error || "HTTP " + response.status);
  return output;
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
    discardEdits();
    await refresh();
  } catch (error) { write("camera-error", error.message); }
  updateButtons();
});
$("start-camera").addEventListener("click", () => action("/api/camera/start"));
$("stop-camera").addEventListener("click", () => action("/api/camera/stop"));
$("apply-settings").addEventListener("click", async () => {
  const gain = Number($("gain").value);
  const exposureMs = Number($("exposure-ms").value);
  if (!Number.isInteger(gain) || gain < 0 || gain > 100 ||
      !Number.isInteger(exposureMs) || exposureMs < 10 || exposureMs > 5000) {
    write("camera-error", "Enter gain 0–100 and exposure 10–5000 ms, as whole numbers");
    return;
  }
  try {
    const result = await post("/api/camera/settings", {gain, exposure_us: exposureMs * 1000});
    pendingSettingsId = result.request_id;
    write("settings-message", "Applying settings…");
    write("camera-error", "");
    updateButtons();
  } catch (error) {
    write("camera-error", error.message);
  }
});
function showProgress(data) {
  currentPhase = data.phase;
  write("camera-phase", "Camera: " + data.phase);
  const fps = typeof data.preview_fps === "number" ? data.preview_fps.toFixed(1) + " fps" : "— fps";
  const capture = typeof data.capture_fps === "number" ? data.capture_fps.toFixed(1) + " raw fps" : "— raw fps";
  const processing = typeof data.preview_processing_ms === "number" ? data.preview_processing_ms.toFixed(0) + " ms processing" : "";
  write("frame-count", (data.frame_number || 0) + " JPEG frames · " + fps + " preview · " + capture + " · " + processing);
  syncSettings(data);
  updateButtons();
  const image = $("preview-image");
  if (!data.has_frame) {
    image.hidden = true;
    $("preview-placeholder").hidden = false;
    previousFrame = -1;
  } else if (data.frame_number !== previousFrame) {
    previousFrame = data.frame_number;
    // Download only NEW JPEGs. Many browser viewers share one backend image.
    image.src = "/api/camera/frame.jpg?frame=" + data.frame_number + "&t=" + Date.now();
    image.hidden = false;
    $("preview-placeholder").hidden = true;
  }
}
async function refresh() {
  const el = $("connection");
  try {
    const response = await fetch("/api/status", {cache: "no-store"});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    el.textContent = token ? "Connected · Controller" : "Connected · Viewer";
    el.className = "connection online";
    write("camera-usb", data.camera.usb_detected ? "Camera USB detected" : "Camera USB not detected");
    if (data.camera.last_error) write("camera-error", data.camera.last_error);
    write("mount-usb", data.mount.usb_detected ? "USB detected" : "USB not detected");
    write("mount-serial", data.mount.serial_present ? "Serial alias available" : "Serial alias unavailable");
    write("storage-state", data.storage.ready ? "Recording drive ready" : data.storage.state.replaceAll("_", " "));
    write("storage-free", freeSpace(data.storage.free_bytes));
    write("pi-temp", data.host.cpu_temperature_c === null ? "Temperature unavailable" : data.host.cpu_temperature_c + " °C");
    const seconds = data.host.uptime_seconds;
    write("pi-uptime", typeof seconds === "number" ? "Uptime: " +
      Math.floor(seconds / 86400) + "d " + Math.floor(seconds % 86400 / 3600) + "h" : "Uptime unavailable");
    write("last-update", new Date(data.utc).toLocaleTimeString());
    showProgress(data.camera);
  } catch (error) {
    el.textContent = "Service unavailable";
    el.className = "connection offline";
  }
}
async function pollPreview() {
  if (progressBusy || !["connecting", "running", "stopping"].includes(currentPhase)) return;
  progressBusy = true;
  try {
    const response = await fetch("/api/camera/progress", {cache: "no-store"});
    if (response.ok) {
      const state = await response.json();
      if (state.last_error) write("camera-error", state.last_error);
      showProgress(state);
    }
  } catch {
    // Main status poll will report connection failures.
  } finally {
    progressBusy = false;
  }
}
async function heartbeat() {
  if (!token) return;
  try { await post("/api/control/heartbeat"); }
  catch { token = null; discardEdits(); updateButtons(); }
}
refresh();
setInterval(refresh, 3000);
setInterval(pollPreview, 200);
setInterval(heartbeat, 5000);
