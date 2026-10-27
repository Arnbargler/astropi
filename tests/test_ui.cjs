"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const EX = [1000,2000,5000,10000,25000,50000,100000,250000,500000,750000,
  1000000,2000000,5000000,10000000,15000000,20000000,25000000,30000000];
const GAIN = [0,5,10,20,30,50,75,100];

function harness() {
  const elements = new Map(), intervals = new Map(), calls = [];
  let camera = {
    phase: "running", has_frame: false, frame_number: 0,
    gain: 0, exposure_us: 100143, settings_applied_id: 0,
    preview_fps: 6.0, capture_fps: 20, preview_processing_ms: 60,
    preview_mode: "auto", debayer: true,
    raw_mean_adu: 150, raw_p99_adu: 300, raw_saturated_percent: 0
  };
  function el(id) {
    if (!elements.has(id)) elements.set(id, {
      value: "", textContent: "", checked: false, hidden: false,
      disabled: false, className: "", src: "", attributes: {}, handlers: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, cb) { this.handlers[name] = cb; },
      dispatch(name) { return this.handlers[name](); }
    });
    return elements.get(id);
  }
  const fetch = async (url, options={}) => {
    const payload = options.body ? JSON.parse(options.body) : {};
    calls.push({url, payload});
    if (url === "/api/status") return {ok:true, json:async()=>({
      camera:{...camera, usb_detected:true},
      mount:{usb_detected:true,serial_present:true},
      storage:{ready:true,free_bytes:1000000000},
      host:{cpu_temperature_c:42,uptime_seconds:3600},
      utc:"2026-10-27T19:00:00Z"
    })};
    if (url === "/api/camera/progress") return {ok:true,json:async()=>({...camera})};
    if (url === "/api/control/take") return {ok:true,json:async()=>({token:"test-token"})};
    if (url === "/api/control/heartbeat") return {ok:true,json:async()=>({ok:true})};
    if (url === "/api/camera/settings") return {ok:true,json:async()=>({
      request_id: calls.filter(c=>c.url==="/api/camera/settings").length,ok:true
    })};
    if (url === "/api/camera/preview-mode") {
      camera = {...camera,preview_mode:payload.mode};
      return {ok:true,json:async()=>({ok:true,mode:payload.mode})};
    }
    if (url === "/api/camera/debayer") {
      camera = {...camera,debayer:payload.enabled};
      return {ok:true,json:async()=>({ok:true,enabled:payload.enabled})};
    }
    throw Error("Unexpected request: "+url);
  };
  const code = fs.readFileSync(path.join(__dirname,"../astropi/static/app.js"),"utf8");
  vm.runInNewContext(code, {
    document:{getElementById:el},
    fetch, setInterval:(fn,ms)=>intervals.set(ms,fn),Date,Number,Math,Promise
  });
  return {el, intervals, calls,
    updateCamera:data=>{camera={...camera,...data}},
    camera:()=>camera,
    flush:()=>new Promise(resolve=>setImmediate(resolve))
  };
}

test("18 exposure and 8 gain native radio buttons have correct values", () => {
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  const input=(name)=>[...html.matchAll(new RegExp('id="'+name+'-(\\d+)" name="'+name+'" value="(\\d+)"','g'))]
    .map(x=>Number(x[1]));
  assert.deepEqual(input("exposure"),EX);
  assert.deepEqual(input("gain"),GAIN);
  assert.doesNotMatch(html,/id="apply-settings"/);
  assert.match(html,/id="debayer-off"/);
  assert.match(html,/id="debayer-on"/);
});

test("selecting exposure or gain immediately sends matching settings", async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("exposure-100000").checked,true);
  assert.equal(h.el("gain-0").checked,true);
  await h.el("take-control").dispatch("click");
  assert.equal(h.el("gain-100").disabled,false);
  await h.el("exposure-250000").dispatch("change");
  let posts=h.calls.filter(c=>c.url==="/api/camera/settings");
  assert.deepEqual(posts[0].payload,{gain:0,exposure_us:250000});
  assert.equal(h.el("exposure-250000").checked,true);
  await h.intervals.get(3000)();
  assert.equal(h.el("exposure-250000").checked,true,"poll must not undo unacknowledged choice");
  await h.el("gain-75").dispatch("change");
  posts=h.calls.filter(c=>c.url==="/api/camera/settings");
  assert.deepEqual(posts[1].payload,{gain:75,exposure_us:250000});
  assert.equal(h.el("gain-75").checked,true);
  h.updateCamera({gain:75,exposure_us:250143,settings_applied_id:2});
  await h.intervals.get(50)();
  assert.equal(h.el("exposure-250000").checked,true);
  assert.equal(h.el("gain-75").checked,true);
  assert.match(h.el("settings-message").textContent,/applied/);
});

test("stretch and debayer toggles send operator-only mode changes",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("debayer-off").dispatch("click");
  assert.equal(h.camera().debayer,false);
  assert.equal(h.el("debayer-off").attributes["aria-pressed"],"true");
  assert.equal(h.el("debayer-on").attributes["aria-pressed"],"false");
  await h.el("stretch-fixed").dispatch("click");
  assert.equal(h.camera().preview_mode,"fixed");
  await h.el("debayer-on").dispatch("click");
  assert.equal(h.camera().debayer,true);
  assert.equal(h.el("debayer-on").attributes["aria-pressed"],"true");
});

test("fast preview polling and frame deduplication are retained",()=>{
  const js=fs.readFileSync(path.join(__dirname,"../astropi/static/app.js"),"utf8");
  assert.match(js,/setInterval\(pollPreview, 50\)/);
  assert.match(js,/data\.frame_number !== previousFrame/);
});
