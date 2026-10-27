"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

test("status polling never overwrites either unapplied camera input", async () => {
  const elements = new Map();
  const intervals = new Map();
  const calls = [];
  let camera = {
    phase: "running", has_frame: false, frame_number: 0,
    gain: 0, exposure_us: 100143, settings_applied_id: 0,
    preview_fps: 1.0, preview_processing_ms: 100,
    preview_mode: "auto", raw_mean_adu: 150, raw_p99_adu: 300, raw_saturated_percent: 0
  };
  function el(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        value: "", textContent: "", hidden: false, disabled: false,
        className: "", src: "", handlers: {},
        addEventListener(name, cb) { this.handlers[name] = cb; },
        dispatch(name) { return this.handlers[name](); }
      });
    }
    return elements.get(id);
  }
  const document = { getElementById: el, activeElement: null };
  const fetch = async (url, options = {}) => {
    calls.push(url);
    if (url === "/api/status") {
      return { ok: true, json: async () => ({
        camera: { ...camera, usb_detected: true },
        mount: { usb_detected: true, serial_present: true },
        storage: { ready: true, free_bytes: 1000000000 },
        host: { cpu_temperature_c: 40, uptime_seconds: 400 },
        utc: "2026-10-27T19:00:00Z"
      }) };
    }
    if (url === "/api/camera/progress") {
      return { ok: true, json: async () => ({...camera}) };
    }
    if (url === "/api/control/take") {
      return {ok: true, json: async () => ({token:"local-test"})};
    }
    if (url === "/api/camera/settings") {
      return {ok: true, json: async () => ({ok: true, request_id: 1})};
    }
    if (url === "/api/camera/preview-mode") {
      camera = {...camera, preview_mode: JSON.parse(options.body).mode};
      return {ok: true, json: async () => ({ok:true, mode:camera.preview_mode})};
    }
    throw Error("Unexpected request " + url);
  };
  const source = fs.readFileSync(path.join(__dirname, "../astropi/static/app.js"), "utf8");
  vm.runInNewContext(source, {
    document, fetch, setInterval: (fn, interval) => intervals.set(interval, fn),
    Date, Number, Math, Promise
  });
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();
  assert.equal(el("gain").value, 0);
  assert.equal(el("exposure-ms").value, 100);
  await el("take-control").dispatch("click");

  document.activeElement = el("exposure-ms");
  el("exposure-ms").value = "250";
  el("exposure-ms").dispatch("input");
  document.activeElement = el("gain");
  el("gain").value = "30";
  el("gain").dispatch("input");
  document.activeElement = el("apply-settings");

  await intervals.get(3000)();
  await intervals.get(200)();
  assert.equal(el("exposure-ms").value, "250");
  assert.equal(el("gain").value, "30");
  assert.match(el("settings-message").textContent, /Unsaved/);

  await el("apply-settings").dispatch("click");
  await intervals.get(3000)();
  assert.equal(el("exposure-ms").value, "250");
  assert.equal(el("gain").value, "30");
  assert.match(el("settings-message").textContent, /Applying/);

  camera = {...camera, gain: 30, exposure_us: 250143, settings_applied_id: 1};
  await intervals.get(200)();
  assert.equal(el("gain").value, 30);
  assert.equal(el("exposure-ms").value, 250);
  assert.match(el("settings-message").textContent, /applied/);
  assert.match(el("raw-metrics").textContent, /RAW mean: 150/);
  el("preview-mode").value = "fixed";
  await el("preview-mode").dispatch("change");
  await intervals.get(200)();
  assert.equal(camera.preview_mode, "fixed");
  assert.equal(el("preview-mode").value, "fixed");
});

test("preview checks run more often than old 1200ms timer and avoid duplicate JPEG loads", async () => {
  const js = fs.readFileSync(path.join(__dirname, "../astropi/static/app.js"), "utf8");
  assert.match(js, /setInterval\(pollPreview, 200\)/);
  assert.doesNotMatch(js, /setInterval\(updateFrame, 1200\)/);
  assert.match(js, /data\.frame_number !== previousFrame/);
});
