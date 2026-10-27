"use strict";
function write(id, text) { document.getElementById(id).textContent = text; }
function freeSpace(bytes) { return typeof bytes === "number" ? (bytes / 1024 ** 3).toFixed(1) + " GiB free" : "Free space unavailable"; }
async function refresh() {
  const el = document.getElementById("connection");
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    el.textContent = "Service connected · Read-only";
    el.className = "connection online";
    write("camera-usb", data.camera.usb_detected ? "USB detected" : "USB not detected");
    write("mount-usb", data.mount.usb_detected ? "USB detected" : "USB not detected");
    write("mount-serial", data.mount.serial_present ? "Serial alias available" : "Serial alias unavailable");
    write("storage-state", data.storage.ready ? "Recording drive ready" : data.storage.state.replaceAll("_", " "));
    write("storage-free", freeSpace(data.storage.free_bytes));
    write("pi-temp", data.host.cpu_temperature_c === null ? "Temperature unavailable" : data.host.cpu_temperature_c + " °C");
    const s = data.host.uptime_seconds;
    write("pi-uptime", typeof s === "number" ? "Uptime: " + Math.floor(s / 86400) + "d " + Math.floor(s % 86400 / 3600) + "h" : "Uptime unavailable");
    write("last-update", new Date(data.utc).toLocaleTimeString());
  } catch (error) {
    el.textContent = "Service unavailable";
    el.className = "connection offline";
  }
}
refresh();
setInterval(refresh, 3000);
