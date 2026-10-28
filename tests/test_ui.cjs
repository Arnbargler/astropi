"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const EX = [1000,2000,5000,10000,25000,50000,100000,250000,500000,750000,
  1000000,2000000,5000000,10000000,15000000,20000000,25000000,30000000];
const GAIN = [0,5,10,20,30,50,75,100];
const BINNING = [1, 2];

function harness() {
  const elements = new Map(), intervals = new Map(), calls = [];
  const documentHandlers = {};
  const windowHandlers = {};
  let documentHidden = false;
  let capture = {phase:"idle",files:[],directory:null,total_frames:0,completed_frames:0,directories:[]};
  let mount = {phase:"disconnected",connected:false,model:null,firmware:null,
    motion_phase:"idle",motion_armed:false,stop_stable:false,motion_warning:null,
    environment_phase:"idle",environment:null,environment_error:null,
    time_sync_phase:"idle",time_sync_error:null,time_sync_verified_utc:null,
    jog_speed:"slow",
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
      camera:{...camera, usb_detected:true}, capture:{...capture},
      mount:{usb_detected:true,serial_present:true,...mount},
      storage:{ready:true,free_bytes:1000000000},
      host:{cpu_temperature_c:42,uptime_seconds:3600},
      utc:"2026-10-27T19:00:00Z"
    })};
    if (url === "/api/camera/binning") {
      camera={...camera,binning:payload.binning,
        width:3856/payload.binning,height:2180/payload.binning};
      return {ok:true,json:async()=>({ok:true,binning:payload.binning})};
    }
    if (url === "/api/camera/progress") return {ok:true,json:async()=>({...camera,capture:{...capture}})};
    if (url === "/api/mount/status") return {ok:true,json:async()=>({...mount})};
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
      mount={...mount,motion_armed:false,motion_phase:"stopping",motion_direction:null};
      return {ok:true,json:async()=>({ok:true,state:"stop_requested"})};
    }
    if (url === "/api/mount/connect") {
      mount = {...mount,phase:"connected",connected:true,model:"AM3N",
        firmware:"1.8.8",altitude_text:"+01*30:50",azimuth_text:"013*43:10",
        ra_text:"12:34:56",dec_text:"-22*15:30",
        tracking:false,slewing:false,at_home:true,altaz_mode:true,
        raw_status:"nNHZM040400990",updated_utc:"2026-10-27T20:00:00+00:00"};
      return {ok:true,json:async()=>({ok:true})};
    }
    if (url === "/api/mount/disconnect") {
      mount = {...mount,phase:"disconnected",connected:false,
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
  const code = fs.readFileSync(path.join(__dirname,"../astropi/static/app.js"),"utf8");
  vm.runInNewContext(code, {
    document:{getElementById:el,
      addEventListener:(name,fn)=>{documentHandlers[name]=fn;},
      get hidden(){return documentHidden;}},
    window:{addEventListener:(name,fn)=>{windowHandlers[name]=fn;}},
    fetch, setInterval:(fn,ms)=>intervals.set(ms,fn),Date,Number,Math,Promise
  });
  return {el, intervals, calls,
    updateCamera:data=>{camera={...camera,...data}},
    camera:()=>camera,
    capture:()=>capture,
    updateCapture:data=>{capture={...capture,...data}},
    mount:()=>mount,
    updateMount:data=>{mount={...mount,...data}},
    documentEvent:kind=>documentHandlers[kind](),
    windowEvent:kind=>windowHandlers[kind](),
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
    assert.equal(h.el("gain-5").disabled,true);
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
  assert.match(h.el("mount-raw-status").textContent,/nNHZM040400990/);
  assert.equal(h.el("mount-connect").disabled,true);
  assert.equal(h.el("mount-disconnect").disabled,false);
  await h.el("mount-disconnect").dispatch("click");
  assert.equal(h.mount().connected,false);
  assert.equal(h.el("mount-altitude").textContent,"—");
  assert.equal(h.el("mount-azimuth").textContent,"—");
  assert.equal(h.el("mount-disconnect").disabled,true);
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

test("mount UI has immediate manual controls but no Home GoTo Park or tracking",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.match(html,/id="mount-connect"/);
  assert.match(html,/id="mount-disconnect"/);
  assert.doesNotMatch(html,/id="mount-(?:home|goto|track|park)"/);
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



test("1080p dashboard is full-width, keeps all functional controls and stays responsive",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  const css=fs.readFileSync(path.join(__dirname,"../astropi/static/style.css"),"utf8");
  assert.match(html,/class="dashboard-grid"/);
  assert.match(html,/class="imaging-column"/);
  assert.match(html,/class="health-strip"/);
  assert.ok(html.indexOf('class="card preview-card"') < html.indexOf('class="card save-panel"'));
  assert.ok(html.indexOf('class="card save-panel"') < html.indexOf('class="card controls"'));
  assert.ok(html.indexOf('class="card controls"') < html.indexOf('class="card mount-card"'));
  assert.ok(html.indexOf('class="mount-jog-panel"') < html.indexOf('class="mount-environment"'),
    "Mount Stop and jog controls are more prominent than secondary clock readbacks");
  for (const id of [
    "preview-image","start-camera","stop-camera","exposure-buttons","gain-buttons",
    "binning-buttons","stretch-auto","stretch-fixed","debayer-on","debayer-off",
    "capture-fits","capture-raw","capture-jpg","capture-png","capture-1",
    "capture-5","capture-50","capture-100","capture-150","capture-200",
    "cancel-sequence","capture-results","mount-connect",
    "mount-disconnect","mount-stop","mount-speed-slow","mount-speed-max",
    "mount-north","mount-south","mount-west","mount-east",
    "mount-env-time","mount-env-latitude","mount-raw-status",
    "storage-state","storage-free","pi-temp","pi-uptime"
  ]) assert.match(html,new RegExp('id="'+id+'"'),"Missing control/status "+id);
  const ids=Array.from(html.matchAll(/\bid="([^"]+)"/g),m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,"No repeated DOM ids");
  assert.match(css,/\.shell\{width:100%;max-width:2160px/);
  assert.doesNotMatch(css,/max-width:1140px/);
  assert.match(css,/\.dashboard-grid\{display:grid;grid-template-columns:minmax\(0,1\.95fr\)/);
  assert.match(css,/\.preview-frame\{width:100%;height:auto;aspect-ratio:3856\/2180/);
  assert.match(css,/@media \(max-width:1550px\)/);
  assert.match(css,/@media \(max-width:920px\)/);
  assert.match(css,/\.imaging-column\{display:contents\}/);
  assert.match(css,/@media \(max-width:650px\)/);
  for(const obsolete of [
    "Choose output formats independently",
    "FITS/RAW16: 3856",
    "Five manual rates:",
    "Exposure/gain presets apply automatically",
    "Binning change restarts the camera session",
    "DEVELOPMENT BUILD"
  ]) assert.ok(!html.includes(obsolete),"Obsolete on-screen instruction: "+obsolete);
  assert.match(html,/Software Stop is not fail-safe/,
    "Physical fallback warning is safety-critical");
});
