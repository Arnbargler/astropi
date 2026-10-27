"use strict";
let token = null;
let hasFrame = false;
let currentPhase = "stopped";
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
  for (const id of ["gain", "exposure-ms", "apply-settings"]) {
    $(id).disabled = !owner || currentPhase !== "running";
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
async function action(path, payload) {
  try {
    await post(path, payload);
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
  try { await post("/api/control/release"); token = null; }
  catch (error) { write("camera-error", error.message); }
  updateButtons();
});
$("start-camera").addEventListener("click", () => action("/api/camera/start"));
$("stop-camera").addEventListener("click", () => action("/api/camera/stop"));
$("apply-settings").addEventListener("click", () => {
  const gain = Number($("gain").value);
  const exposureMs = Number($("exposure-ms").value);
  if (!Number.isInteger(gain) || gain < 0 || gain > 100 ||
      !Number.isInteger(exposureMs) || exposureMs < 10 || exposureMs > 5000) {
    write("camera-error", "Enter gain 0–100 and exposure 10–5000 ms, as whole numbers");
    return;
  }
  action("/api/camera/settings", {gain, exposure_us: exposureMs * 1000});
});
async function refresh() {
  const el = $("connection");
  try {
    const response = await fetch("/api/status", {cache: "no-store"});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    el.textContent = token ? "Connected · Controller" : "Connected · Viewer";
    el.className = "connection online";
    currentPhase = data.camera.phase;
    hasFrame = data.camera.has_frame;
    write("camera-usb", data.camera.usb_detected ? "Camera USB detected" : "Camera USB not detected");
    write("camera-phase", "Camera: " + data.camera.phase);
    write("frame-count", data.camera.frame_number + " preview frames");
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
    if (document.activeElement !== $("gain")) $("gain").value = data.camera.gain;
    if (document.activeElement !== $("exposure-ms")) $("exposure-ms").value = Math.round(data.camera.exposure_us / 1000);
    updateButtons();
  } catch (error) {
    el.textContent = "Service unavailable";
    el.className = "connection offline";
  }
}
function updateFrame() {
  const image = $("preview-image");
  if (!hasFrame) {
    image.hidden = true;
    $("preview-placeholder").hidden = false;
    return;
  }
  image.src = "/api/camera/frame.jpg?t=" + Date.now();
  image.hidden = false;
  $("preview-placeholder").hidden = true;
}
async function heartbeat() {
  if (!token) return;
  try { await post("/api/control/heartbeat"); }
  catch { token = null; updateButtons(); }
}
refresh();
setInterval(refresh, 3000);
setInterval(updateFrame, 1200);
setInterval(heartbeat, 5000);
