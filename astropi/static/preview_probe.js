"use strict";
// Optional, self-contained diagnostic for the browser delivery path.
// Load from Chrome Console; NOT imported by app.js or the default page.
(() => {
  if (window.AstroPiPreviewProbe) {
    console.info("AstroPi preview probe is already running. Use AstroPiPreviewProbe.report().");
    return;
  }

  const images = ["preview-image", "preview-image-buffer"]
    .map(id => document.getElementById(id))
    .filter(Boolean);
  if (images.length !== 2) {
    console.error("AstroPi preview probe: both JPEG image elements are required.");
    return;
  }

  const clock = () => performance.now();
  const round = n => Number.isFinite(n) ? Math.round(n) : null;
  const age = (stamp, now) => stamp === null ? null : round(now - stamp);
  const cap = (arr, item, max = 80) => {
    arr.push(item);
    if (arr.length > max) arr.shift();
  };

  const probeStart = clock();
  const stats = {
    startedUTC: new Date().toISOString(),
    progress: {started:0, completed:0, errors:0, inFlight:0,
      lastStart:null, lastDone:null, lastDuration:null, longestDuration:0},
    status: {started:0, completed:0, errors:0, inFlight:0,
      lastStart:null, lastDone:null, lastDuration:null, longestDuration:0},
    image: {started:0, loaded:0, errors:0, lastSrc:null, lastLoad:null,
      lastDuration:null, longestDuration:0, lastRequestedFrame:null,
      lastLoadedFrame:null},
    loopMaxGapMs: 0,
    gaps: [],
    recentSlowRequests: []
  };
  const beginByImage = new Map();
  const loadHandlers = [];
  let previousTick = clock();
  let gapOpen = null;
  const GAP_MS = 550;
  const originalFetch = window.fetch;

  function readState(now) {
    return {
      utc: new Date().toISOString(),
      frameDisplay: document.getElementById("frame-count")?.textContent || "",
      cameraPhase: document.getElementById("camera-phase")?.textContent || "",
      documentHidden: document.hidden,
      progressAgeMs: age(stats.progress.lastDone, now),
      progressStartedAgeMs: age(stats.progress.lastStart, now),
      progressInFlight: stats.progress.inFlight,
      lastProgressRttMs: round(stats.progress.lastDuration),
      imageLoadAgeMs: age(stats.image.lastLoad, now),
      imageSrcAgeMs: age(stats.image.lastSrc, now),
      imageRequestedFrame: stats.image.lastRequestedFrame,
      imageLoadedFrame: stats.image.lastLoadedFrame,
      lastImageLoadMs: round(stats.image.lastDuration),
      longestBrowserTickMs: round(stats.loopMaxGapMs)
    };
  }

  function frameFromSrc(src) {
    try {
      const f = new URL(src, location.href).searchParams.get("frame");
      return f === null ? null : Number(f);
    } catch {
      return null;
    }
  }

  function imageRequested(image) {
    if (!image.getAttribute("src")) return;
    const t = clock();
    beginByImage.set(image, t);
    stats.image.lastSrc = t;
    stats.image.started++;
    stats.image.lastRequestedFrame = frameFromSrc(image.src);
  }

  function imageLoaded(image, error) {
    const now = clock();
    if (error) stats.image.errors++;
    else {
      stats.image.loaded++;
      stats.image.lastLoad = now;
      stats.image.lastLoadedFrame = frameFromSrc(image.src);
      const started = beginByImage.get(image);
      if (started !== undefined) {
        stats.image.lastDuration = now - started;
        stats.image.longestDuration = Math.max(stats.image.longestDuration,
          stats.image.lastDuration);
      }
      if (gapOpen) {
        const record = {
          durationMs: round(now - gapOpen.lastLoadAt),
          atUTC: new Date().toISOString(),
          whenDetected: gapOpen.snapshot,
          whenRecovered: readState(now)
        };
        cap(stats.gaps, record, 40);
        console.warn("AstroPi JPEG gap: " + record.durationMs + " ms", record.whenDetected);
        gapOpen = null;
      }
    }
    beginByImage.delete(image);
  }

  const observer = new MutationObserver(changes => {
    for (const change of changes) {
      if (change.attributeName === "src")
        imageRequested(change.target);
    }
  });
  for (const img of images) {
    observer.observe(img, {attributes:true,attributeFilter:["src"]});
    const onLoad = () => imageLoaded(img, false);
    const onError = () => imageLoaded(img, true);
    img.addEventListener("load", onLoad);
    img.addEventListener("error", onError);
    loadHandlers.push([img, onLoad, onError]);
  }

  window.fetch = function(resource, options) {
    let path = "";
    try {
      const source = typeof resource === "string" ? resource : resource?.url;
      if (source) path = new URL(source, location.href).pathname;
    } catch { /* Preserve original fetch behavior for unknown URL shapes. */ }
    const key = path === "/api/camera/progress" ? "progress" :
      path === "/api/status" ? "status" : null;
    if (!key) return originalFetch.apply(this, arguments);

    const state = stats[key];
    const start = clock();
    state.started++;
    state.inFlight++;
    state.lastStart = start;

    const finish = ok => {
      const now = clock();
      state.inFlight--;
      state.lastDone = now;
      state.lastDuration = now - start;
      state.longestDuration = Math.max(state.longestDuration, state.lastDuration);
      if (ok) state.completed++;
      else state.errors++;
      if (state.lastDuration >= 250)
        cap(stats.recentSlowRequests, {
          utc:new Date().toISOString(),kind:key,ms:round(state.lastDuration),ok
        }, 30);
    };
    try {
      return originalFetch.apply(this, arguments).then(
        response => {finish(response.ok);return response;},
        error => {finish(false);throw error;}
      );
    } catch (error) {
      finish(false);
      throw error;
    }
  };

  const interval = setInterval(() => {
    const now = clock();
    stats.loopMaxGapMs = Math.max(stats.loopMaxGapMs, now - previousTick);
    previousTick = now;
    const phase = document.getElementById("camera-phase")?.textContent || "";
    if (document.hidden || !phase.includes("running")) {
      gapOpen = null;
      return;
    }
    const lastLoad = stats.image.lastLoad;
    if (lastLoad !== null && now - lastLoad >= GAP_MS && !gapOpen) {
      gapOpen = {lastLoadAt:lastLoad,snapshot:readState(now)};
    }
  }, 100);

  window.AstroPiPreviewProbe = {
    report() {
      const now = clock();
      console.log("AstroPi preview probe summary", {
        uptimeSeconds:round((now - probeStart) / 1000),
        startedUTC:stats.startedUTC,
        progress:stats.progress,
        fullStatus:stats.status,
        image:stats.image,
        loopMaxGapMs:round(stats.loopMaxGapMs),
        jpegGapsDetected:stats.gaps.length,
        slowHttpRequests:stats.recentSlowRequests.length,
        current:readState(now)
      });
      console.table(stats.gaps.map(g=>({
        UTC:g.atUTC,
        gapMs:g.durationMs,
        progressAgeAtGapMs:g.whenDetected.progressAgeMs,
        progressInFlight:g.whenDetected.progressInFlight,
        jpegSrcAgeAtGapMs:g.whenDetected.imageSrcAgeMs,
        imageFrame:g.whenDetected.imageLoadedFrame,
        requestedFrame:g.whenDetected.imageRequestedFrame,
        loopMaxGapMs:g.whenDetected.longestBrowserTickMs
      })));
      console.table(stats.recentSlowRequests);
      return {gaps:stats.gaps,slowRequests:stats.recentSlowRequests};
    },
    stop() {
      clearInterval(interval);
      observer.disconnect();
      for(const [img, onLoad, onError] of loadHandlers) {
        img.removeEventListener("load", onLoad);
        img.removeEventListener("error", onError);
      }
      if (window.fetch === wrappedFetch) window.fetch = originalFetch;
      delete window.AstroPiPreviewProbe;
      console.info("AstroPi preview probe stopped; fetch restored.");
    }
  };
  const wrappedFetch = window.fetch;
  console.info("AstroPi preview probe running. After several freezes, run AstroPiPreviewProbe.report(); stop with AstroPiPreviewProbe.stop().");
})();
