"use strict";
// Offline VirtualSky adapter for Find. Informational only: NO mount APIs or motion.
(() => {
  const LAT = 45.2933;
  const LON = -75.8571; // east-positive; AM3N serial site is west-positive
  const DATA = "/static/vendor/virtualsky/messier.json";
  const $ = id => document.getElementById(id);
  let sky = null, catalogue = new Map(), active = false, loading = null;
  let utcAnchor = null, monotonicAnchor = null, selected = null;
  const now = () => performance.now();
  const piNow = () => utcAnchor === null ? null : new Date(utcAnchor + (now() - monotonicAnchor));
  const note = message => { $("atlas-status").textContent = message; };

  function updateTarget() {
    if (!selected || !catalogue.has(selected)) return;
    const utc = piNow();
    if (!utc) return;
    const object = catalogue.get(selected);
    const pos = window.AstroPiCoordinates.position(
      object.ra.decimal, object.dec.decimal, utc, LAT, LON);
    $("atlas-target-readout").hidden = false;
    $("atlas-altitude").textContent = pos.altitudeDeg.toFixed(1) + "°";
    $("atlas-azimuth").textContent = Math.abs(pos.altitudeDeg) >= 89.9999
      ? "Undefined (zenith/nadir)" : pos.azimuthDeg.toFixed(1) + "°";
    const above = pos.altitudeDeg >= 0;
    $("atlas-visibility").textContent = above
      ? "Above geometric horizon" : "Below geometric horizon";
    $("atlas-visibility").className = above ? "atlas-above" : "atlas-below";
  }

  function syncUTC(value) {
    const millis = Date.parse(value);
    if (!Number.isFinite(millis)) return;
    utcAnchor = millis;
    monotonicAnchor = now();
    if (sky && active) updateClock();
    if (active && !sky && !loading) {
      loading = initialize().catch(error => {
        loading = null; note("Atlas unavailable: " + error.message);
      });
    }
  }

  function updateClock() {
    const clock = piNow();
    if (!clock) return;
    $("atlas-time").textContent = "Pi UTC: " + clock.toISOString().replace("T", " ").slice(0, 19);
    if (sky && active) sky.setClock(clock);
    if (active) updateTarget();
  }

  function targetName(text) {
    const match = /^M\s*0*([1-9]\d{0,2})$/i.exec(text.trim());
    if (!match) return null;
    const number = Number(match[1]);
    return number <= 110 ? "M" + number : null;
  }

  function selectObject(name) {
    const key = targetName(name);
    const object = catalogue.get(key);
    if (!object || !sky) {
      note("No Messier match. Enter M1 through M110.");
      return false;
    }
    if (selected && selected !== key) {
      const old = sky.pointers.find(pointer => pointer.label === selected);
      if (old) old.colour = "#b4c9d5";
    }
    selected = key;
    const pointer = sky.pointers.find(item => item.label === key);
    if (pointer) pointer.colour = "#ffcf78";
    $("atlas-search").value = key;
    $("atlas-selection").textContent =
      key + " · RA " + object.ra.h + "h " + object.ra.m + "m " +
      object.ra.s + "s · Dec " + object.dec.d + "° " + object.dec.m +
      "′ " + object.dec.s + "″";
    sky.selectProjection("gnomic");
    sky.setFOV(45);
    sky.setRADec(object.ra.decimal, object.dec.decimal).draw();
    updateTarget();
    note(key + " selected. Chart centred; mount unchanged.");
    return true;
  }

  function allSky() {
    if (!sky) return;
    sky.selectProjection("polar");
    sky.draw();
    note("Horizon view: N / E / S / W. Pan by dragging.");
  }

  function zoom(direction) {
    if (!sky) return;
    if (sky.projection.id !== "gnomic") {
      sky.selectProjection("gnomic");
      if (selected) {
        const object = catalogue.get(selected);
        sky.setRADec(object.ra.decimal, object.dec.decimal);
      } else {
        sky.setRADec((sky.times.LST * 15) % 360, LAT);
      }
      sky.setFOV(60);
    }
    sky.changeFOV(direction).draw();
  }

  async function initialize() {
    // Catalogue is fetched locally. Never pass names to VirtualSky's online resolver.
    const response = await fetch(DATA, {cache:"force-cache"});
    if (!response.ok) throw Error("Local Messier catalogue is unavailable");
    const entries = await response.json();
    if (!Array.isArray(entries) || entries.length !== 110)
      throw Error("Expected exactly 110 local Messier targets");
    const parsed = new Map();
    for (const item of entries) {
      const name = item && item.target && item.target.name;
      if (!name || !/^M([1-9]|[1-9]\d|10\d|110)$/.test(name) ||
          !item.ra || !item.dec || !Number.isFinite(item.ra.decimal) ||
          !Number.isFinite(item.dec.decimal) || parsed.has(name))
        throw Error("Invalid or duplicate Messier catalogue entry");
      parsed.set(name, item);
    }
    if (!window.AstroPiCoordinates ||
        typeof window.AstroPiCoordinates.position !== "function")
      throw Error("Local coordinate calculations did not load");
    if (!window.S || typeof window.S.virtualsky !== "function")
      throw Error("Local VirtualSky scripts did not load");
    catalogue = parsed;
    const options = $("atlas-messier-options");
    for (let i = 1; i <= 110; i++) {
      const option = document.createElement("option");
      option.value = "M" + i;
      options.appendChild(option);
    }
    sky = window.S.virtualsky({
      id: "atlas-sky", projection: "polar", latitude: LAT, longitude: LON,
      clock: piNow(), lang:"en", keyboard:false, mouse:true, credit:false,
      showdate:false, showposition:false, showstars:true, showplanets:true,
      showplanetlabels:true, constellations:true, constellationlabels:true,
      cardinalpoints:true, gridlines_az:false, gridlines_eq:false,
      gradient:false, background:"#07111e", magnitude:5.5,
      callback: {click: event => {
        if (Number.isInteger(event.matched) && event.matched >= 0 &&
            sky.pointers[event.matched])
          selectObject(sky.pointers[event.matched].label);
      }}
    });
    // Explicit text-only HTML prevents VirtualSky's default remote Wikisky images.
    for (const [key, object] of parsed) {
      sky.addPointer({
        ra:object.ra.decimal, dec:object.dec.decimal, label:key,
        colour:"#b4c9d5", d:4, html:"<strong>" + key + "</strong>"
      });
    }
    updateClock();
    sky.draw();
    window.requestAnimationFrame(() => { if (active) sky.resize(); });
    note("Offline sky ready · 110 Messier targets. Click a marker or search by M-number.");
  }

  async function show() {
    active = true;
    // Get fresh PI time on entry, independently of mount connection.
    try {
      const response = await fetch("/api/status", {cache:"no-store"});
      if (response.ok) syncUTC((await response.json()).utc);
    } catch (_) { /* Existing 3-second app polling will retry. */ }
    if (!active) return;
    if (utcAnchor === null) {
      note("Waiting for the Pi's UTC clock…");
      return;
    }
    if (sky) {
      sky.resize();
      updateClock();
      return;
    }
    if (!loading) {
      note("Loading offline sky catalogue…");
      loading = initialize().catch(error => {
        loading = null; note("Atlas unavailable: " + error.message);
      });
    }
    await loading;
  }

  function hide() { active = false; }
  $("atlas-search-form").addEventListener("submit", event => {
    event.preventDefault();
    selectObject($("atlas-search").value);
  });
  $("atlas-allsky").addEventListener("click", allSky);
  $("atlas-zoom-in").addEventListener("click", () => zoom(1));
  $("atlas-zoom-out").addEventListener("click", () => zoom(-1));
  $("atlas-constellations").addEventListener("change", event => {
    if (!sky) return;
    sky.constellation.lines = event.target.checked;
    sky.constellation.labels = event.target.checked;
    sky.checkLoaded();
    sky.draw();
  });
  $("atlas-grid").addEventListener("change", event => {
    if (sky) { sky.grid.eq = event.target.checked; sky.draw(); }
  });
  window.addEventListener("resize", () => {
    if (sky && active) sky.resize();
  });
  // A steady local clock between Pi's periodic authoritative UTC samples.
  setInterval(() => { if (active) updateClock(); }, 1000);
  window.AstroPiAtlas = {show, hide, syncUTC};
})();
