"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const EX = [1000,2000,5000,10000,25000,50000,100000,250000,500000,750000,
  1000000,2000000,5000000,10000000,15000000,20000000,25000000,30000000];
const GAIN = [0,50,100,260,350,450,550,650];
const BINNING = [1, 2];

function harness() {
  const elements = new Map(), intervals = new Map(), calls = [];
  const timeouts = new Map();
  let nextTimeoutId = 1;
  let holdNextStatus = false, heldStatusReply = null, heldStatusOverride = null;
  const documentHandlers = {};
  const windowHandlers = {};
  let documentHidden = false;
  let capture = {phase:"idle",files:[],directory:null,total_frames:0,completed_frames:0,directories:[]};
  let mount = {phase:"disconnected",connected:false,model:null,firmware:null,
    motion_phase:"idle",motion_armed:false,stop_stable:false,motion_warning:null,
    environment_phase:"idle",environment:null,environment_error:null,
    time_sync_phase:"idle",time_sync_error:null,time_sync_verified_utc:null,
    site_sync_phase:"idle",site_sync_error:null,site_sync_verified_utc:null,
    jog_speed:"slow",tracking:null,tracking_phase:"idle",tracking_target:null,
    tracking_error:null,tracking_status_error:null,
    north_level_confirmed:false,north_level_confirmed_utc:null,
    home_phase:"idle",home_error:null,home_requested_utc:null,
    altitude_text:null,azimuth_text:null,ra_text:null,dec_text:null,
    raw_status:null,updated_utc:null,last_error:null};
  let camera = {
    phase: "running", has_frame: false, frame_number: 0,
    gain: 0, exposure_us: 100143, settings_applied_id: 0,
    binning: 1, width: 3856, height: 2180,
    preview_fps: 6.0, capture_fps: 20, preview_processing_ms: 60,
    preview_mode: "auto", debayer: true,
    raw_mean_adu: 150, raw_p99_adu: 300, raw_saturated_percent: 0
  };
  function el(id) {
    if (!elements.has(id)) elements.set(id, {
      id, value: "", textContent: "", checked: false, hidden: false,
      tabIndex: 0, parentNode: null, focused: false,
      disabled: false, inert: false, className: "", src: "", style: {},
       attributes: {}, handlers: {}, srcChanges: [],
       onload: null, onerror: null,
       removeAttribute(name) { if (name === "src") this.src = ""; },
       getBoundingClientRect() { return {bottom:72}; },
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, cb) { this.handlers[name] = cb; },
      appendChild(child) { child.parentNode = this; return child; },
      focus() { this.focused = true; },
      dispatch(name, event={}) { return this.handlers[name](event); }
    });
    return elements.get(id);
  }
  const fetch = async (url, options={}) => {
    const payload = options.body ? JSON.parse(options.body) : {};
    calls.push({url, payload});
    if (url === "/api/status") {
      // Take the snapshot NOW, but optionally delay its HTTP completion.
      // This reproduces an older full-status result arriving after a
      // faster camera-progress poll has already updated the browser.
      const snapshot = {
        camera:{...camera, usb_detected:true,...(heldStatusOverride || {})},
        capture:{...capture},
        mount:{usb_detected:true,serial_present:true,...mount},
        storage:{ready:true,free_bytes:1000000000},
        host:{cpu_temperature_c:42,uptime_seconds:3600},
        utc:"2026-10-27T19:00:00Z"
      };
      const reply = {ok:true,json:async()=>snapshot};
      if (holdNextStatus) {
        holdNextStatus = false;
        heldStatusOverride = null;
        return new Promise(resolve=>{heldStatusReply=()=>{heldStatusReply=null;resolve(reply);};});
      }
      return reply;
    }
    if (url === "/api/camera/binning") {
      camera={...camera,binning:payload.binning,
        width:3856/payload.binning,height:2180/payload.binning};
      return {ok:true,json:async()=>({ok:true,binning:payload.binning})};
    }
    if (url === "/api/camera/progress") return {ok:true,json:async()=>({...camera,capture:{...capture}})};
    if (url === "/api/mount/status") return {ok:true,json:async()=>({...mount})};
    if (url === "/api/mount/environment/sync") {
      mount = {...mount,time_sync_phase:"checking",site_sync_phase:"checking"};
      return {ok:true,json:async()=>({ok:true,state:"queued"})};
    }
    if (url === "/api/mount/az-home") {
      mount={...mount,home_phase:"queued",motion_phase:"home_queued",
             home_error:null,home_requested_utc:"2026-10-31T22:55:00Z"};
      return {ok:true,json:async()=>({ok:true,state:"queued"})};
    }
    if (url === "/api/mount/north-level") {
      mount={...mount,north_level_confirmed:payload.confirmed,
        north_level_confirmed_utc:payload.confirmed ? "2026-10-31T23:55:00Z" : null};
      return {ok:true,json:async()=>({ok:true,confirmed:payload.confirmed})};
    }
    if (url === "/api/mount/tracking") {
      mount = {...mount,tracking_phase:"queued",tracking_target:payload.enabled,
        tracking_error:null};
      return {ok:true,json:async()=>({ok:true,state:"queued",enabled:payload.enabled})};
    }
    if (url === "/api/mount/environment/read") {
      mount = {...mount,environment_phase:"queued"};
      return {ok:true,json:async()=>({ok:true,state:"queued"})};
    }
    if (url === "/api/mount/jog") {
      mount={...mount,motion_armed:true,motion_phase:"moving",
        motion_direction:payload.direction};
      return {ok:true,json:async()=>({ok:true,direction:payload.direction})};
    }
    if (url === "/api/mount/jog-heartbeat")
      return {ok:true,json:async()=>({ok:true})};
    if (url === "/api/mount/stop") {
      mount={...mount,motion_armed:false,motion_phase:"stopping",motion_direction:null,
        home_phase:["queued","sending","slewing"].includes(mount.home_phase) ? "aborted" : mount.home_phase};
      return {ok:true,json:async()=>({ok:true,state:"stop_requested"})};
    }
    if (url === "/api/mount/connect") {
      mount = {...mount,phase:"connected",connected:true,model:"AM3N",
        north_level_confirmed:false,north_level_confirmed_utc:null,
        home_phase:"idle",home_error:null,home_requested_utc:null,
        firmware:"1.8.8",altitude_text:"+01*30:50",azimuth_text:"013*43:10",
        ra_text:"12:34:56",dec_text:"-22*15:30",
        tracking:false,tracking_phase:"idle",tracking_target:null,
        slewing:false,at_home:true,altaz_mode:true,
        raw_status:"nNHZM040400990",updated_utc:"2026-10-27T20:00:00+00:00"};
      return {ok:true,json:async()=>({ok:true})};
    }
    if (url === "/api/mount/disconnect") {
      mount = {...mount,phase:"disconnected",connected:false,
        north_level_confirmed:false,north_level_confirmed_utc:null,
        tracking:null,tracking_phase:"idle",tracking_target:null,
        motion_phase:"idle",motion_armed:false,
        altitude_text:null,azimuth_text:null,ra_text:null,dec_text:null,
        raw_status:null,updated_utc:null};
      return {ok:true,json:async()=>({ok:true})};
    }
    if (url === "/api/control/take") return {ok:true,json:async()=>({token:"test-token"})};
    if (url === "/api/control/release") return {ok:true,json:async()=>({ok:true})};
    if (url === "/api/control/heartbeat") return {ok:true,json:async()=>({ok:true})};
    if (url === "/api/capture/sequence") {
      capture = {phase:"waiting",id:"sequence-mock",total_frames:payload.count,
        completed_frames:0,formats:payload.formats,files:[],directories:[]};
      return {ok:true,json:async()=>({ok:true,id:"sequence-mock",count:payload.count})};
    }
    if (url === "/api/capture/cancel") {
      capture = {...capture,phase:"cancelled",cancel_requested:true};
      return {ok:true,json:async()=>({ok:true,id:capture.id})};
    }
    if (url === "/api/capture") {
      capture = {phase:"waiting",id:"mock-1",formats:payload.formats,files:[]};
      return {ok:true,json:async()=>({ok:true,id:"mock-1"})};
    }
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
  // The real template initially checks FITS and JPG; emulate those DOM defaults.
  el("capture-fits").checked = true;
  el("capture-jpg").checked = true;
  el("preview-image").hidden = true;
  el("preview-image-buffer").hidden = true;
  el("shared-preview-card").parentNode = el("fotograph-preview-slot");
  el("shared-camera-controls").parentNode = el("fotograph-controls-slot");
  const code = fs.readFileSync(path.join(__dirname,"../astropi/static/app.js"),"utf8");
  vm.runInNewContext(code, {
    document:{getElementById:el,
      addEventListener:(name,fn)=>{documentHandlers[name]=fn;},
      get hidden(){return documentHidden;}},
    window:{addEventListener:(name,fn)=>{windowHandlers[name]=fn;}},
    fetch, setInterval:(fn,ms)=>intervals.set(ms,fn),
    setTimeout:(fn,ms)=>{const id=nextTimeoutId++;timeouts.set(id,{fn,ms});return id;},
    clearTimeout:id=>timeouts.delete(id),Date,Number,Math,Promise
  });
  return {el, intervals, timeouts, calls,
    holdStatus:(override=null)=>{holdNextStatus=true;heldStatusOverride=override;},
    releaseStatus:()=>{if(!heldStatusReply)throw Error("No delayed full-status response");
                       heldStatusReply();},
    expirePreview:()=>{
      const entry=[...timeouts.entries()].find(([id,t])=>t.ms===2000);
      if (!entry) throw Error("No pending preview timeout");
      timeouts.delete(entry[0]);
      entry[1].fn();
    },
    updateCamera:data=>{camera={...camera,...data}},
    camera:()=>camera,
    capture:()=>capture,
    updateCapture:data=>{capture={...capture,...data}},
    mount:()=>mount,
    updateMount:data=>{mount={...mount,...data}},
    documentEvent:kind=>documentHandlers[kind](),
    windowEvent:(kind,event={})=>windowHandlers[kind](event),
    setHidden:flag=>{documentHidden=flag;},
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
  assert.equal(h.el("gain-650").disabled,false);
  await h.el("exposure-250000").dispatch("change");
  let posts=h.calls.filter(c=>c.url==="/api/camera/settings");
  assert.deepEqual(posts[0].payload,{gain:0,exposure_us:250000});
  assert.equal(h.el("exposure-250000").checked,true);
  await h.intervals.get(3000)();
  assert.equal(h.el("exposure-250000").checked,true,"poll must not undo unacknowledged choice");
  await h.el("gain-650").dispatch("change");
  posts=h.calls.filter(c=>c.url==="/api/camera/settings");
  assert.deepEqual(posts[1].payload,{gain:650,exposure_us:250000});
  assert.equal(h.el("gain-650").checked,true);
  h.updateCamera({gain:650,exposure_us:250143,settings_applied_id:2});
  await h.intervals.get(50)();
  assert.equal(h.el("exposure-250000").checked,true);
  assert.equal(h.el("gain-650").checked,true);
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
  assert.match(js,/queuePreview\(data\)/);
  assert.match(js,/previewNewestFrame > previewRequestedFrame/);
  assert.match(js,/previewInFlight/);
});


test("JPEG loader preserves the visible frame and requests only the latest after completion",async()=>{
  const h=harness();
  await h.flush();
  const first=h.el("preview-image"),second=h.el("preview-image-buffer");
  h.updateCamera({phase:"running",has_frame:true,frame_number:101});
  await h.intervals.get(50)();
  assert.match(second.src,/frame=101/);
  assert.equal(first.hidden,true, "original image remains hidden before first load");
  assert.equal(second.hidden,true, "pending buffer stays hidden until load");
  assert.equal(h.el("preview-placeholder").hidden,false);
  assert.equal(h.timeouts.size,1);
  h.updateCamera({frame_number:102});
  await h.intervals.get(50)();
  h.updateCamera({frame_number:110});
  await h.intervals.get(50)();
  assert.match(second.src,/frame=101/,"no new request while first is loading");
  assert.equal(first.src,"","main image remains untouched");
  assert.equal(h.timeouts.size,1,"only one outstanding preview deadline");
  second.onload();
  assert.equal(second.hidden,false);
  assert.equal(first.hidden,true);
  assert.equal(h.el("preview-placeholder").hidden,true);
  assert.match(first.src,/frame=110/,"skip 102-109 and request latest immediately");
  assert.equal(h.timeouts.size,1);
  h.updateCamera({frame_number:111});
  await h.intervals.get(50)();
  assert.match(first.src,/frame=110/,"one outstanding replacement at a time");
  first.onload();
  assert.equal(first.hidden,false);
  assert.equal(second.hidden,true);
  assert.match(second.src,/frame=111/);
  second.onload();
  assert.equal(h.timeouts.size,0);
  assert.equal(h.calls.filter(c=>c.url==="/api/camera/frame.jpg").length,0,
    "JPEGs are actual browser image downloads, not extra fetch requests");
});

test("late full-status frame rollback cannot reset a newer preview",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({phase:"running",has_frame:true,frame_number:100});
  await h.intervals.get(50)();
  b.onload();
  assert.equal(b.hidden,false);

  h.holdStatus(); // Snapshots frame 100, but response will be delayed.
  const stale=h.intervals.get(3000)();
  h.updateCamera({frame_number:120});
  await h.intervals.get(50)();
  assert.match(a.src,/frame=120/);
  a.onload();
  assert.equal(a.hidden,false);
  assert.equal(b.hidden,true);
  assert.match(h.el("frame-count").textContent,/120 JPEG frames/);

  h.releaseStatus();
  await stale;
  assert.equal(a.hidden,false,"late 100 must not reset 120 or hide it");
  assert.equal(b.hidden,true);
  assert.match(h.el("frame-count").textContent,/120 JPEG frames/,
    "old full status must not roll back displayed counters");
  assert.equal(h.timeouts.size,0);
  h.updateCamera({frame_number:121});
  await h.intervals.get(50)();
  assert.match(b.src,/frame=121/,"live preview still accepts newer frames");
});

test("late stopped/full-status snapshot cannot stop a running preview",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({phase:"running",has_frame:true,frame_number:200});
  await h.intervals.get(50)();
  b.onload();
  assert.equal(b.hidden,false);

  h.holdStatus({phase:"stopped",has_frame:false,frame_number:0});
  const stale=h.intervals.get(3000)();
  h.updateCamera({frame_number:202});
  await h.intervals.get(50)();
  a.onload();
  assert.equal(a.hidden,false);
  assert.equal(b.hidden,true);

  h.releaseStatus();
  await stale;
  assert.equal(a.hidden,false,"old stopped response must not hide preview");
  assert.equal(b.hidden,true);
  assert.match(h.el("camera-phase").textContent,/running/);
  assert.match(h.el("frame-count").textContent,/202 JPEG frames/);
  h.updateCamera({frame_number:203});
  await h.intervals.get(50)();
  assert.match(b.src,/frame=203/);
});

test("newest camera restart still resets frame counter and JPEG buffer",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({phase:"running",has_frame:true,frame_number:500});
  await h.intervals.get(50)();
  b.onload();
  assert.equal(b.hidden,false);
  h.updateCamera({frame_number:2});
  await h.intervals.get(50)();
  assert.equal(b.hidden,true,"actual current frame rollback invalidates previous image");
  assert.equal(h.el("preview-placeholder").hidden,false);
  assert.match(b.src,/frame=2/);
  b.onload();
  assert.equal(b.hidden,false);
});

test("failed JPEG leaves previous image visible and recovers with newest frame",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({has_frame:true,frame_number:2});
  await h.intervals.get(50)();
  b.onload();
  assert.equal(b.hidden,false);
  assert.equal(h.el("preview-placeholder").hidden,true);
  h.updateCamera({frame_number:3});
  await h.intervals.get(50)();
  const stale=a.onerror;
  h.updateCamera({frame_number:5});
  await h.intervals.get(50)();
  stale();
  assert.equal(b.hidden,false,"failure must keep last good frame visible");
  assert.match(a.src,/frame=5/,"newer frame must be scheduled after failure");
  a.onload();
  assert.equal(a.hidden,false);
  assert.equal(b.hidden,true);
  assert.equal(h.timeouts.size,0);
});

test("JPEG timeout abandons only pending image and moves on to newer frame",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({has_frame:true,frame_number:10});
  await h.intervals.get(50)();
  b.onload();
  h.updateCamera({frame_number:11});
  await h.intervals.get(50)();
  const abandonedLoad=a.onload;
  h.updateCamera({frame_number:20});
  await h.intervals.get(50)();
  h.expirePreview();
  assert.equal(b.hidden,false);
  assert.match(a.src,/frame=20/);
  abandonedLoad(); // Old network event must not replace new frame.
  assert.equal(b.hidden,false);
  a.onload();
  assert.equal(a.hidden,false);
  assert.equal(h.timeouts.size,0);
});

test("stopping or restarting camera discards stale JPEG completions",async()=>{
  const h=harness();
  await h.flush();
  const a=h.el("preview-image"),b=h.el("preview-image-buffer");
  h.updateCamera({phase:"running",has_frame:true,frame_number:123});
  await h.intervals.get(50)();
  const stale=b.onload;
  h.updateCamera({phase:"stopped",has_frame:false,frame_number:123});
  await h.intervals.get(3000)();
  assert.equal(h.timeouts.size,0);
  assert.equal(b.src,"");
  assert.equal(a.src,"");
  assert.equal(a.hidden,true);
  assert.equal(b.hidden,true);
  assert.equal(h.el("preview-placeholder").hidden,false);
  stale();
  assert.equal(h.el("preview-placeholder").hidden,false,
    "image from old camera session must never be shown");
  h.updateCamera({phase:"running",has_frame:true,frame_number:1});
  await h.intervals.get(3000)();
  assert.match(b.src,/frame=1/,"new camera session can reuse same image elements");
  b.onload();
  assert.equal(b.hidden,false);
  assert.equal(h.timeouts.size,0);
  h.updateCamera({frame_number:0});
  await h.intervals.get(50)();
  assert.equal(b.hidden,true,"frame count rollback invalidates old image");
  assert.equal(h.el("preview-placeholder").hidden,false);
});

test("preview buffer and in-flight image survive Focus/Find/Fotograph switches",async()=>{
  const h=harness();
  await h.flush();
  h.updateCamera({has_frame:true,frame_number:9});
  await h.intervals.get(50)();
  const pending=h.el("preview-image-buffer");
  await h.el("tab-focus").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("tab-fotograph").dispatch("click");
  assert.match(pending.src,/frame=9/);
  pending.onload();
  assert.equal(pending.hidden,false);
  assert.equal(h.el("shared-preview-card").parentNode.id,"fotograph-preview-slot");
  assert.equal(h.timeouts.size,0);
});

test("compact capture toggles submit exactly selected formats for one frame", async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("capture-1").disabled,true,"viewers cannot record");
  await h.el("take-control").dispatch("click");
  assert.equal(h.el("capture-1").disabled,false);
  await h.el("capture-1").dispatch("click");
  assert.deepEqual(h.calls.filter(call=>call.url==="/api/capture")[0].payload,
                   {formats:["fits","jpg"]});
  await h.intervals.get(50)();
  assert.equal(h.el("capture-1").disabled,true,"only one capture may be pending");
  h.updateCapture({phase:"done",directory:"captures/shot1",
    files:[{format:"FITS",path:"captures/shot1/a.fits",bytes:16800000},
           {format:"JPG",path:"captures/shot1/a.jpg",bytes:40000}]});
  await h.intervals.get(50)();
  assert.equal(h.el("capture-1").disabled,false);
  assert.match(h.el("capture-results").textContent,/captures\/shot1\/a.fits/);
  h.el("capture-fits").checked=false;
  h.el("capture-jpg").checked=false;
  h.el("capture-raw").checked=true;
  h.el("capture-png").checked=true;
  h.el("capture-raw").dispatch("change");
  await h.el("capture-1").dispatch("click");
  assert.deepEqual(h.calls.filter(call=>call.url==="/api/capture")[1].payload,
                   {formats:["raw","png"]});
  assert.equal(h.calls.filter(call=>call.url==="/api/capture/sequence").length,0);
});

test("capture buttons are disabled with no formats and return when reselected",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  for(const name of ["fits","raw","jpg","png"]) h.el("capture-"+name).checked=false;
  h.el("capture-fits").dispatch("change");
  for(const count of [1,5,50,100,150,200])
    assert.equal(h.el("capture-"+count).disabled,true);
  h.el("capture-jpg").checked=true;
  h.el("capture-jpg").dispatch("change");
  assert.equal(h.el("capture-200").disabled,false);
});

test("fixed sequence buttons submit correct count and lock until complete",async()=>{
  for (const count of [5,50,100,150,200]) {
    const h=harness();
    await h.flush();
    await h.el("take-control").dispatch("click");
    h.el("capture-fits").checked=true;
    h.el("capture-jpg").checked=true;
    h.el("capture-raw").checked=false;
    h.el("capture-png").checked=false;
    assert.equal(h.el("capture-"+count).disabled,false);
    await h.el("capture-"+count).dispatch("click");
    const sends=h.calls.filter(c=>c.url==="/api/capture/sequence");
    assert.equal(sends.length,1);
    assert.deepEqual(sends[0].payload,{count,formats:["fits","jpg"]});
    await h.intervals.get(50)();
    for(const other of [1,5,50,100,150,200])
      assert.equal(h.el("capture-"+other).disabled,true);
    assert.equal(h.el("gain-650").disabled,true);
    assert.equal(h.el("cancel-sequence").disabled,false);
    h.updateCapture({phase:"saving",completed_frames:2,current_frame:3, total_frames:count});
    await h.intervals.get(50)();
    assert.match(h.el("sequence-progress").textContent,new RegExp("2 / "+count));
    h.updateCapture({phase:"done",completed_frames:count,
      directories:["captures/first","captures/last"]});
    await h.intervals.get(50)();
    assert.equal(h.el("capture-"+count).disabled,false);
    assert.equal(h.el("cancel-sequence").disabled,true);
    assert.match(h.el("capture-results").textContent,/captures\/last/);
  }
});

test("Cancel only operates during an active multi-frame sequence",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("cancel-sequence").disabled,true);
  await h.el("take-control").dispatch("click");
  await h.el("capture-1").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,true,"one frame is not a sequence");
  h.updateCapture({phase:"done",files:[]});
  await h.intervals.get(50)();
  await h.el("capture-5").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,false);
  await h.el("cancel-sequence").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,true);
  assert.match(h.el("capture-state").textContent,/cancelled/);
  assert.equal(h.calls.filter(c=>c.url==="/api/capture/cancel").length,1);
});

test("capture UI offers only the six fixed frame counts",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.match(html,/class="capture-presets"/);
  assert.match(html,/class="format-switch"/);
  for (const n of [1,5,50,100,150,200])
    assert.match(html,new RegExp('id="capture-'+n+'"'));
  assert.doesNotMatch(html,/id="sequence-count"/);
  assert.doesNotMatch(html,/id="start-sequence"/);
  assert.doesNotMatch(html,/id="capture-now"/);
  assert.match(html,/id="cancel-sequence"/);
});

test("mount telemetry viewer remains read-only; operator explicitly connects",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-connect").disabled,true);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/connect").length,0,
    "initial page load must never open the serial port");
  await h.el("take-control").dispatch("click");
  assert.equal(h.el("mount-connect").disabled,false);
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.mount().connected,true);
  assert.equal(h.el("mount-altitude").textContent,"+01*30:50");
  assert.equal(h.el("mount-azimuth").textContent,"013*43:10");
  assert.equal(h.el("mount-ra").textContent,"12:34:56");
  assert.equal(h.el("mount-dec").textContent,"-22*15:30");
  assert.match(h.el("mount-flags").textContent,/not tracking/);
  assert.equal(h.el("mount-tracking-status").textContent,"Tracking: OFF");
  assert.match(h.el("mount-raw-status").textContent,/nNHZM040400990/);
  assert.equal(h.el("mount-connect").disabled,true);
  assert.equal(h.el("mount-disconnect").disabled,false);
  await h.el("mount-disconnect").dispatch("click");
  assert.equal(h.mount().connected,false);
  assert.equal(h.el("mount-altitude").textContent,"—");
  assert.equal(h.el("mount-azimuth").textContent,"—");
  assert.equal(h.el("mount-disconnect").disabled,true);
});

test("tracking ON/OFF requires control and verified time/site; mount readback drives display",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-tracking-on").disabled,true);
  assert.match(h.el("mount-tracking-status").textContent,/UNKNOWN/);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-tracking-on").disabled,true);
  assert.equal(h.el("mount-tracking-off").disabled,true); // already OFF
  h.updateMount({tracking:true}); // Even unverified UTC, OFF must be available
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-off").disabled,false);
  h.updateMount({tracking:false,time_sync_phase:"verified",site_sync_phase:"verified"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-on").disabled,false);
  await h.el("mount-tracking-on").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/tracking").length,1);
  assert.equal(h.calls.find(c=>c.url==="/api/mount/tracking").payload.enabled,true);
  assert.equal(h.el("mount-tracking-on").disabled,true);
  assert.match(h.el("mount-tracking-action").textContent,/queued/);
  h.updateMount({tracking:true,tracking_phase:"verified"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-status").textContent,"Tracking: ON");
  assert.equal(h.el("mount-tracking-off").disabled,false);
  assert.equal(h.el("mount-sync-environment").disabled,true);
  await h.el("mount-tracking-off").dispatch("click");
  assert.deepEqual(h.calls.filter(c=>c.url==="/api/mount/tracking").map(c=>c.payload.enabled),[true,false]);
  h.updateMount({tracking:false,tracking_phase:"verified"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-status").textContent,"Tracking: OFF");
  assert.equal(h.el("mount-sync-environment").disabled,false);
  h.updateMount({tracking:null,tracking_status_error:"Unexpected :GAT# reply"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-status").textContent,"Tracking: UNKNOWN");
  assert.match(h.el("mount-tracking-error").textContent,/GAT/);
  h.updateMount({tracking:false,tracking_phase:"error",tracking_error:"AM3N rejected tracking ON"});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-tracking-error").textContent,/rejected tracking ON/);
  h.updateMount({tracking_phase:"idle",tracking_error:null,tracking_status_error:null,
                 motion_phase:"goto_slewing"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-tracking-on").disabled,true);
  assert.equal(h.el("mount-tracking-off").disabled,true);
});

test("Az Home is Alt/Az only, STOP-interruptible, and telemetry-verified",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-az-home").disabled,true);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  h.updateMount({tracking:true,at_home:null});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-az-home").disabled,true,"Tracking ON blocks Home");
  h.updateMount({tracking:false,altaz_mode:null});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-az-home").disabled,true,"Unknown mode blocks Az Home");
  h.updateMount({altaz_mode:true});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-az-home").disabled,false);
  await h.el("mount-az-home").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/az-home").length,1);
  assert.equal(h.el("mount-az-home").disabled,true);
  assert.match(h.el("mount-az-home-status").textContent,/queued/);
  h.updateMount({home_phase:"slewing",motion_phase:"home_slewing",
                 tracking:null,tracking_status_error:"Unexpected :GAT# reply: 'e5'"});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-az-home-status").textContent,/moving/);
  assert.equal(h.el("mount-stop").disabled,false);
  assert.equal(h.el("mount-tracking-on").disabled,true);
  await h.el("mount-stop").dispatch("click");
  await h.intervals.get(1000)(); // Home status follows the next mount telemetry poll.
  assert.match(h.el("mount-az-home-status").textContent,/interrupted/);
  h.updateMount({home_phase:"completed",motion_phase:"idle",at_home:true,
                 tracking:false,tracking_status_error:null});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-az-home-status").textContent,/completed/);
  assert.equal(h.el("mount-az-home").disabled,false);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/tracking").length,0);
});

test("North / Level is a manual physical checkpoint, never a Home command",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-north-level-confirm").disabled,true);
  assert.match(h.el("mount-north-level-status").textContent,/not confirmed/);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-north-level-confirm").disabled,false);
  h.updateMount({tracking:true});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-north-level-confirm").disabled,true,
    "Tracking ON must prevent physical setup confirmation");
  h.updateMount({tracking:null,at_home:null});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-north-level-confirm").disabled,true);
  assert.match(h.el("mount-north-level-home").textContent,/verify native Home manually/);
  h.updateMount({tracking:false,at_home:null});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-north-level-confirm").disabled,false,
    "Absent Home flag is UNKNOWN, not a blocker for manual confirmation");
  await h.el("mount-north-level-confirm").dispatch("click");
  const requests=h.calls.filter(c=>c.url==="/api/mount/north-level");
  assert.equal(requests.length,1);
  assert.equal(requests[0].payload.confirmed,true);
  assert.match(h.el("mount-north-level-status").textContent,/CONFIRMED/);
  assert.equal(h.el("mount-north-level-confirm").disabled,true);
  assert.equal(h.el("mount-north-level-clear").disabled,false);
  h.updateMount({motion_phase:"goto_slewing"});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-north-level-status").textContent,/CONFIRMED/,
    "GoTo does not invalidate the physical starting reference");
  await h.el("mount-north-level-clear").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/north-level").length,2);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/north-level")[1].payload.confirmed,false);
  assert.match(h.el("mount-north-level-status").textContent,/not confirmed/);
  h.updateMount({motion_phase:"idle"});
  await h.intervals.get(1000)();
  await h.el("mount-north-level-confirm").dispatch("click");
  await h.el("mount-disconnect").dispatch("click");
  assert.match(h.el("mount-north-level-status").textContent,/not confirmed/);
  assert.equal(h.el("mount-north-level-confirm").disabled,true);
  assert.equal(h.el("mount-north-level-clear").disabled,true);
  assert.equal(h.calls.filter(c=>/mount\/(?:home|sync|align)/.test(c.url)).length,0,
    "Physical confirmation must never send mount motor/coordinate commands");
});

test("lost mount data is never shown as fresh pointing",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  h.updateMount({phase:"error",connected:false,
    last_error:"Serial port disappeared", altitude_text:"+01*30:50"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-altitude").textContent,"—");
  assert.equal(h.el("mount-ra").textContent,"—");
  assert.match(h.el("mount-error").textContent,/Serial port disappeared/);
  assert.equal(h.el("mount-connect").disabled,false);
});

test("mount UI has tracking and Az Home without Set Home or Park",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.match(html,/id="mount-connect"/);
  assert.match(html,/id="mount-disconnect"/);
  assert.doesNotMatch(html,/id="mount-(?:home|goto|park)(?:["-])/);
  assert.match(html,/id="mount-tracking-on"/);
  assert.match(html,/id="mount-tracking-off"/);
  assert.match(html,/id="mount-az-home"/);
  assert.match(html,/id="mount-stop"/);
  assert.doesNotMatch(html,/id="mount-arm"/);
  assert.match(html,/id="mount-speed-slew"/);
  assert.match(html,/id="mount-speed-max"/);
});


test("motion buttons start immediately for operator, no arm step",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-north").disabled,true);
  assert.equal(h.el("mount-stop").disabled,true);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-stop").disabled,false);
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  assert.equal(h.el("mount-north").disabled,false);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,0);
  assert.equal(h.el("mount-east").disabled,false);
  await h.el("mount-east").dispatch("pointerdown");
  let requests=h.calls.filter(c=>c.url==="/api/mount/jog");
  assert.equal(requests.length,1);
  assert.equal(requests[0].payload.direction,"east");
  assert.equal(requests[0].payload.speed,"slow");
  await h.intervals.get(150)();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog-heartbeat").length,1);
  h.documentEvent("pointerup");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  assert.equal(h.el("mount-east").disabled,true,
    "cannot restart until Stop/axes stability is confirmed");
  h.updateMount({motion_phase:"idle",stop_stable:true});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-east").disabled,false,
    "subsequent jog starts without separate arm");
});

test("window blur and visibility change request Stop",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  await h.el("mount-north").dispatch("pointerdown");
  h.windowEvent("blur");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  await h.el("mount-west").dispatch("pointerdown");
  h.setHidden(true);
  h.documentEvent("visibilitychange");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,2);
});

test("emergency stop is available in the UI without owning operator lease",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("release-control").dispatch("click");
  assert.equal(h.el("mount-east").disabled,true);
  assert.equal(h.el("mount-stop").disabled,false);
  await h.el("mount-stop").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
});


test("mount speed presets bind to immediate jogs and lock while moving",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  assert.equal(h.el("mount-speed-slow").checked,true);
  assert.equal(h.el("mount-speed-medium").disabled,false);
  h.el("mount-speed-medium").dispatch("change");
  assert.equal(h.el("mount-speed-medium").checked,true);
  await h.el("mount-east").dispatch("pointerdown");
  assert.equal(h.el("mount-speed-fast").disabled,true);
  assert.equal(h.el("mount-west").disabled,true);
  assert.equal(h.el("mount-east").disabled,false);
  const requests=h.calls.filter(x=>x.url==="/api/mount/jog");
  assert.equal(requests.length,1);
  assert.deepEqual(requests[0].payload,{direction:"east",speed:"medium"});
  h.documentEvent("pointerup");
  await h.flush();
  assert.equal(h.el("mount-speed-fast").disabled,true);
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-speed-fast").disabled,false);
});

test("reconnect always restores slow mount speed",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  h.el("mount-speed-fast").dispatch("change");
  assert.equal(h.el("mount-speed-fast").checked,true);
  await h.el("mount-disconnect").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-speed-slow").checked,true);
});



test("mount clock/site button is operator-only and renders read-only responses", async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-read-environment").disabled,true);
  assert.equal(h.calls.filter(x=>x.url==="/api/mount/environment/read").length,0);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-read-environment").disabled,false);
  await h.el("mount-read-environment").dispatch("click");
  assert.equal(h.calls.filter(x=>x.url==="/api/mount/environment/read").length,1);
  h.updateMount({environment_phase:"ready",
    environment_updated_utc:"2026-10-28T07:41:24Z",
    environment:{utc_offset:"+00:00",date:"10/28/26",local_time:"07:41:24",
      latitude:"+45*17:36",longitude_west:"+075*51:26",sidereal_time:"12:32:54"}});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-env-latitude").textContent,"+45*17:36");
  assert.equal(h.el("mount-env-longitude").textContent,"+075*51:26");
  assert.equal(h.el("mount-env-time").textContent,"07:41:24");
  assert.equal(h.el("mount-env-offset").textContent,"+00:00");
  assert.equal(h.el("mount-env-sidereal").textContent,"12:32:54");
  await h.el("mount-disconnect").dispatch("click");
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-env-longitude").textContent,"—");
  assert.equal(h.el("mount-read-environment").disabled,true);
});

test("clock/site queries have no setter controls or browser-side serial commands",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.match(html,/id="mount-read-environment"/);
  assert.doesNotMatch(html,/id="mount-(?:set-time|set-location|set-date|sync-clock)"/);
});


test("720x and 1440x are selected without arm, with release Stop", async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  h.el("mount-speed-slew").dispatch("change");
  assert.equal(h.el("mount-speed-slew").checked,true);
  await h.el("mount-north").dispatch("pointerdown");
  const sends=h.calls.filter(c=>c.url==="/api/mount/jog");
  assert.deepEqual(sends[0].payload,{direction:"north",speed:"slew"});
  h.documentEvent("pointerup");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  h.el("mount-speed-max").dispatch("change");
  assert.equal(h.el("mount-speed-max").checked,true);
  await h.el("mount-west").dispatch("pointerdown");
  const second=h.calls.filter(c=>c.url==="/api/mount/jog");
  assert.deepEqual(second[1].payload,{direction:"west",speed:"max"});
  h.documentEvent("pointerup");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,2);
});


test("mount automatically synced clock status is visible without clicking read button",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  h.updateMount({
    time_sync_phase:"verified",time_sync_error:null,
    time_sync_verified_utc:"2026-10-28T08:33:07+00:00",
    environment_phase:"ready",environment_updated_utc:"2026-10-28T08:33:07+00:00",
    environment:{utc_offset:"+00:00",date:"10/28/26",local_time:"08:33:07",
      latitude:"+45*17:36",longitude_west:"+075*51:26",sidereal_time:"12:45:00"}
  });
  await h.intervals.get(1000)();
  assert.match(h.el("mount-time-sync").textContent,/VERIFIED/);
  assert.equal(h.el("mount-env-date").textContent,"10/28/26");
  assert.equal(h.el("mount-env-time").textContent,"08:33:07");
  assert.equal(h.el("mount-env-latitude").textContent,"+45*17:36");
  assert.equal(h.calls.filter(x=>x.url==="/api/mount/environment/read").length,0);
});

test("NTP unavailable shows honest error while mount remains connected",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  h.updateMount({time_sync_phase:"error",
    time_sync_error:"Pi has not confirmed NTP sync",
    time_sync_verified_utc:null});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-time-sync").textContent,/NOT synchronized/);
  assert.match(h.el("mount-time-sync-error").textContent,/not confirmed NTP/);
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  assert.equal(h.el("mount-east").disabled,false,
    "manual Alt/Az is still available without a verified sky clock");
});


test("camera binning buttons appear under Gain and select correct API values",async()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.ok(html.indexOf('id="binning-buttons"') > html.indexOf('id="gain-buttons"'));
  assert.match(html,/id="binning-1"/);
  assert.match(html,/id="binning-2"/);
  assert.doesNotMatch(html,/id="binning-3"/);
  assert.doesNotMatch(html,/id="binning-4"/);
  const h=harness();
  await h.flush();
  assert.equal(h.el("binning-2").disabled,true);
  await h.el("take-control").dispatch("click");
  assert.equal(h.el("binning-2").disabled,false);
  await h.el("binning-2").dispatch("change");
  assert.equal(h.calls.filter(x=>x.url==="/api/camera/binning").length,1);
  assert.deepEqual(h.calls.filter(x=>x.url==="/api/camera/binning")[0].payload,
                   {binning:2});
  assert.equal(h.el("binning-2").checked,true);
  assert.match(h.el("binning-readback").textContent,/1928×1090/);
  await h.el("binning-1").dispatch("change");
  assert.equal(h.el("binning-1").checked,true);
});

test("binning buttons disabled while a capture or sequence is saving",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  h.updateCapture({phase:"saving",total_frames:5,completed_frames:2});
  await h.intervals.get(50)();
  assert.equal(h.el("binning-1").disabled,true);
  assert.equal(h.el("binning-2").disabled,true);
  h.updateCapture({phase:"idle",total_frames:0});
  await h.intervals.get(50)();
  assert.equal(h.el("binning-2").disabled,false);
});



test("persistent three tabs retain single camera preview and controls",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("panel-fotograph").hidden,false);
  assert.equal(h.el("panel-focus").hidden,true);
  assert.equal(h.el("panel-find").hidden,true);
  assert.equal(h.el("tab-fotograph").attributes["aria-selected"],"true");
  await h.el("take-control").dispatch("click");
  await h.el("gain-260").dispatch("change");
  await h.el("tab-focus").dispatch("click");
  assert.equal(h.el("panel-focus").hidden,false);
  assert.equal(h.el("panel-fotograph").hidden,true);
  assert.equal(h.el("shared-preview-card").parentNode.id,"focus-preview-slot");
  assert.equal(h.el("shared-camera-controls").parentNode.id,"focus-controls-slot");
  assert.equal(h.el("gain-260").checked,true);
  assert.equal(h.el("release-control").hidden,false,"operator lease remains active");
  let prevented=false;
  await h.el("tab-focus").dispatch("keydown",{
    key:"ArrowRight",preventDefault(){prevented=true;}
  });
  assert.equal(prevented,true);
  assert.equal(h.el("panel-find").hidden,false);
  assert.equal(h.el("tab-find").focused,true);
  await h.el("tab-fotograph").dispatch("click");
  assert.equal(h.el("shared-preview-card").parentNode.id,"fotograph-preview-slot");
  assert.equal(h.el("shared-camera-controls").parentNode.id,"fotograph-controls-slot");
  assert.equal(h.el("gain-260").checked,true);
  for(const path of ["/api/camera/start","/api/camera/stop",
    "/api/control/release","/api/capture/cancel"])
    assert.equal(h.calls.filter(c=>c.url===path).length,0,
      "tab switching must not affect backend "+path);
});

test("leaving Find during a held jog requests Stop before hiding controls",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("tab-find").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  await h.el("mount-north").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,1);
  await h.el("tab-focus").dispatch("click");
  assert.equal(h.el("panel-find").hidden,true);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  assert.equal(h.el("mount-drawer").inert,false,"drawer stays open across tabs");
  assert.equal(h.el("mount-north").disabled,true,"Stop must settle before next jog");
  await h.intervals.get(150)();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog-heartbeat").length,0,
    "no jog heartbeat continues after tab switch");
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-west").disabled,false,"jog available in Focus when drawer open");
  await h.el("mount-west").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,2);
  h.documentEvent("pointerup");
});

test("slide-out mount controls work in every tab without altering workspace",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  assert.equal(h.el("mount-drawer-toggle").attributes["aria-expanded"],"true");
  assert.equal(h.el("mount-drawer").inert,false);
  assert.match(h.el("mount-drawer").className,/is-open/);
  assert.equal(h.el("mount-drawer").style.top,"72px");
  assert.equal(h.el("mount-drawer-close").focused,true);
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-north").disabled,false,
    "Fotograph must allow mount jogging when shared drawer is open");
  for (const tab of ["focus","find","fotograph"]) {
    await h.el("tab-"+tab).dispatch("click");
    assert.equal(h.el("mount-drawer").inert,false,"drawer remains open in "+tab);
    assert.equal(h.el("mount-north").disabled,false);
    assert.equal(h.el("mount-stop").disabled,false);
  }
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,0,
    "idle tab switching must not send Stop");
  await h.el("mount-drawer-close").dispatch("click");
  assert.equal(h.el("mount-drawer").inert,true);
  assert.equal(h.el("mount-drawer-toggle").attributes["aria-expanded"],"false");
  assert.equal(h.el("mount-north").disabled,true);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,0,
    "closing an idle drawer must not send Stop");
  assert.equal(h.el("mount-drawer-toggle").focused,true);
});

test("drawer close, Escape and tab changes send Stop on held jog",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("mount-east").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,1);
  await h.el("mount-drawer-close").dispatch("click");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  assert.equal(h.el("mount-drawer").inert,true);
  await h.intervals.get(150)();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog-heartbeat").length,0);
  await h.el("mount-west").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,1,
    "closed drawer cannot start jog");
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  await h.el("mount-drawer-toggle").dispatch("click");
  await h.el("tab-focus").dispatch("click");
  await h.el("mount-west").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,2);
  let prevented=false;
  h.windowEvent("keydown",{key:"Escape",preventDefault(){prevented=true;}});
  await h.flush();
  assert.equal(prevented,true);
  assert.equal(h.el("mount-drawer").inert,true);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,2);
  assert.equal(h.el("mount-stop").disabled,false,
    "global Stop remains accessible regardless of drawer state after settling");
});

test("closed drawer cannot trigger mount motion but viewer can always Stop",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("mount-drawer-toggle").dispatch("click");
  assert.equal(h.el("mount-east").disabled,true);
  await h.el("mount-east").dispatch("pointerdown");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,0);
  await h.el("release-control").dispatch("click");
  await h.el("mount-stop").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
});

test("emergency Stop remains available to viewer on every tab",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("release-control").dispatch("click");
  for(const tab of ["focus","find","fotograph"]){
    await h.el("tab-"+tab).dispatch("click");
    assert.equal(h.el("mount-stop").disabled,false);
    await h.el("mount-stop").dispatch("click");
  }
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,3);
});

test("capture sequence persists across workspace switches",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("capture-5").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,false);
  await h.el("tab-find").dispatch("click");
  h.updateCapture({phase:"saving",total_frames:5,completed_frames:3});
  await h.intervals.get(50)();
  assert.match(h.el("global-capture-state").textContent,/3\/5/);
  await h.el("tab-focus").dispatch("click");
  await h.el("tab-fotograph").dispatch("click");
  assert.equal(h.el("cancel-sequence").disabled,false);
  assert.equal(h.calls.filter(c=>c.url==="/api/capture/cancel").length,0);
  assert.equal(h.calls.filter(c=>c.url==="/api/control/release").length,0);
});

test("failed GoTo remains explicit after Stop confirms stationary axes",async()=>{
  const h=harness();
  await h.flush();
  h.updateMount({phase:"connected",connected:true,motion_phase:"stopping",
    goto_phase:"error",goto_target:"M76",
    goto_error:"AM3N rejected :Sr (reply b'E1#')",
    last_stop_reason:"GoTo command failed",stop_stable:false});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-motion").textContent,/GoTo M76 FAILED.*rejected :Sr/);
  assert.match(h.el("mount-error").textContent,/rejected :Sr/);
  assert.match(h.el("global-mount-alert").textContent,/GoTo M76 FAILED/);
  h.updateMount({motion_phase:"idle",stop_stable:true});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-motion").textContent,/GoTo M76 FAILED/);
  assert.match(h.el("global-mount-alert").textContent,/rejected :Sr/);
  // Next accepted GoTo clears the old, unrelated failure.
  h.updateMount({goto_phase:"slewing",goto_error:null,
                 goto_target:"M31",motion_phase:"goto_slewing",stop_stable:false});
  await h.intervals.get(1000)();
  assert.doesNotMatch(h.el("mount-motion").textContent,/M76 FAILED/);
});

test("manual time and permanent-site synchronization requires idle controlled mount",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-sync-environment").disabled,true);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-sync-environment").disabled,false);
  await h.el("mount-sync-environment").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/environment/sync").length,1);
  h.updateMount({time_sync_phase:"verified",site_sync_phase:"verified",
                 site_sync_error:null,site_sync_verified_utc:"2026-10-31T22:00:00Z"});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-site-sync").textContent,/VERIFIED/);
  h.updateMount({motion_phase:"moving"});
  await h.intervals.get(1000)();
  assert.equal(h.el("mount-sync-environment").disabled,true);
  h.updateMount({motion_phase:"idle",site_sync_phase:"error",
                 site_sync_error:"Site readback mismatch"});
  await h.intervals.get(1000)();
  assert.match(h.el("mount-environment-error").textContent,/Site readback mismatch/);
});

test("global mount warning exposes uncertain stop while other tab is visible",async()=>{
  const h=harness();
  await h.flush();
  h.updateMount({phase:"connected",connected:true,
    motion_phase:"uncertain",motion_warning:"Stop unverified"});
  await h.intervals.get(1000)();
  assert.match(h.el("global-mount-alert").textContent,/PHYSICAL CANCEL/);
  assert.equal(h.el("panel-fotograph").hidden,false);
});

test("three workspaces retain responsive controls and safety warnings",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  const css=fs.readFileSync(path.join(__dirname,"../astropi/static/style.css"),"utf8");
  assert.match(html,/role="tablist"/);
  for(const name of ["focus","find","fotograph"]){
    assert.match(html,new RegExp('id="tab-'+name+'" role="tab"'));
    assert.match(html,new RegExp('id="panel-'+name+'"'));
  }
  assert.match(html,/id="shared-preview-card"/);
  assert.match(html,/id="shared-camera-controls"/);
  assert.match(html,/id="fotograph-preview-slot"/);
  assert.match(html,/id="focus-controls-slot"/);
  assert.ok(html.indexOf('id="mount-stop"') < html.indexOf('id="panel-focus"'),
    "Emergency Stop must be outside hidden tab panels");
  assert.match(html,/id="mount-drawer-toggle"/);
  assert.match(html,/id="mount-drawer-close"/);
  assert.match(html,/<aside id="mount-drawer"[^>]+aria-hidden="true" inert>/);
  assert.ok(html.indexOf('class="card mount-card"') > html.indexOf('id="panel-fotograph"'),
    "Shared mount card must be outside all workspace panels");
  assert.ok(html.indexOf('class="card mount-card"') < html.indexOf('<footer>'));
  assert.equal((html.match(/class="card mount-card"/g)||[]).length,1,
    "One shared mount panel, never duplicate controls");
  assert.ok(html.indexOf('class="card preview-card"') < html.indexOf('class="card save-panel"'));
  assert.ok(html.indexOf('class="card save-panel"') < html.indexOf('class="card controls"'));
  assert.ok(html.indexOf('class="mount-jog-panel"') < html.indexOf('class="mount-environment"'));
  for (const id of [
    "preview-image","start-camera","stop-camera","exposure-buttons","gain-buttons",
    "binning-buttons","stretch-auto","stretch-fixed","debayer-on","debayer-off",
    "capture-fits","capture-raw","capture-jpg","capture-png","capture-1",
    "capture-5","capture-50","capture-100","capture-150","capture-200",
    "cancel-sequence","capture-results","mount-connect",
    "mount-disconnect","mount-stop","mount-sync-environment","mount-site-sync",
    "mount-tracking-on","mount-tracking-off","mount-tracking-status","mount-tracking-error",
    "mount-north-level-confirm","mount-north-level-clear","mount-north-level-status",
    "mount-north-level-home","mount-north-level-error",
    "mount-az-home","mount-az-home-status","mount-az-home-error",
    "mount-speed-slow","mount-speed-max",
    "mount-north","mount-south","mount-west","mount-east",
    "mount-env-time","mount-env-latitude","mount-raw-status",
    "storage-state","storage-free","pi-temp","pi-uptime",
    "global-camera-state","global-mount-state","global-capture-state","global-mount-alert"
  ]) assert.match(html,new RegExp('id="'+id+'"'),"Missing control/status "+id);
  const ids=Array.from(html.matchAll(/\bid="([^"]+)"/g),m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,"No duplicate DOM IDs");
  assert.match(css,/\.shell\{width:100%;max-width:2160px/);
  assert.match(css,/\.global-status\{position:sticky/);
  assert.match(css,/\.mount-drawer\{position:fixed/);
  assert.match(css,/transform:translateX\(105%\)/);
  assert.match(css,/\.mount-drawer\.is-open/);
  assert.match(css,/\.dashboard-grid,\.focus-layout,\.find-layout\{display:grid/);
  assert.match(css,/\.preview-frame\{width:100%;height:auto;aspect-ratio:3856\/2180/);
  assert.match(css,/@media \(max-width:1550px\)/);
  assert.match(css,/@media \(max-width:920px\)/);
  assert.match(css,/\.imaging-column\{display:contents\}/);
  assert.match(css,/@media \(max-width:650px\)/);
  assert.match(html,/Software Stop is not fail-safe/);
  assert.match(html,/id="atlas-sky"/);
  assert.match(html,/id="atlas-search"/);
  assert.match(html,/vendor\/virtualsky\/virtualsky\.min\.js/);
  assert.match(html,/id="atlas-grid"/);
  assert.match(html,/<button type="button" id="atlas-goto" disabled\b/);
  assert.doesNotMatch(html,/id="mount-(?:home|goto|park)(?:["-])/);
  assert.match(html,/id="mount-tracking-on"/);
  assert.match(html,/id="mount-tracking-off"/);
});
