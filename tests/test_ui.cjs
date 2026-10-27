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
  const documentHandlers = {};
  const windowHandlers = {};
  let documentHidden = false;
  let capture = {phase:"idle",files:[],directory:null,total_frames:0,completed_frames:0,directories:[]};
  let mount = {phase:"disconnected",connected:false,model:null,firmware:null,
    motion_phase:"idle",motion_armed:false,stop_stable:false,motion_warning:null,
    altitude_text:null,azimuth_text:null,ra_text:null,dec_text:null,
    raw_status:null,updated_utc:null,last_error:null};
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
      camera:{...camera, usb_detected:true}, capture:{...capture},
      mount:{usb_detected:true,serial_present:true,...mount},
      storage:{ready:true,free_bytes:1000000000},
      host:{cpu_temperature_c:42,uptime_seconds:3600},
      utc:"2026-10-27T19:00:00Z"
    })};
    if (url === "/api/camera/progress") return {ok:true,json:async()=>({...camera,capture:{...capture}})};
    if (url === "/api/mount/status") return {ok:true,json:async()=>({...mount})};
    if (url === "/api/mount/arm") {
      mount={...mount,motion_armed:true,stop_stable:false,motion_phase:"idle"};
      return {ok:true,json:async()=>({ok:true})};
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


test("independent format toggles save the selected combination and report paths", async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("capture-now").disabled,true,"viewers cannot record");
  h.el("capture-fits").checked=true;
  h.el("capture-jpg").checked=true;
  h.el("capture-raw").checked=false;
  h.el("capture-png").checked=false;
  await h.el("take-control").dispatch("click");
  assert.equal(h.el("capture-now").disabled,false);
  await h.el("capture-now").dispatch("click");
  const submitted=h.calls.filter(call=>call.url==="/api/capture");
  assert.equal(submitted.length,1);
  assert.deepEqual(submitted[0].payload,{formats:["fits","jpg"]});
  await h.intervals.get(50)();
  assert.equal(h.el("capture-now").disabled,true,"only one capture may be pending");
  h.updateCapture({phase:"done",directory:"captures/shot1",
    files:[{format:"FITS",path:"captures/shot1/a.fits",bytes:16800000},
           {format:"JPG",path:"captures/shot1/a.jpg",bytes:40000}]});
  await h.intervals.get(50)();
  assert.equal(h.el("capture-now").disabled,false);
  assert.match(h.el("capture-results").textContent,/captures\/shot1\/a.fits/);
  h.el("capture-fits").checked=false;
  h.el("capture-jpg").checked=false;
  h.el("capture-now").disabled=false;
  h.el("capture-raw").checked=true;
  h.el("capture-png").checked=true;
  await h.el("capture-now").dispatch("click");
  const submissions=h.calls.filter(call=>call.url==="/api/capture");
  assert.deepEqual(submissions[1].payload,{formats:["raw","png"]});
});

test("save controls are disabled when no formats are selected",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  for(const name of ["fits","raw","jpg","png"]) h.el("capture-"+name).checked=false;
  h.el("capture-fits").dispatch("change");
  assert.equal(h.el("capture-now").disabled,true);
});


test("sequence frame count submits formats and does not require browser to stay open",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  h.el("capture-fits").checked=true;
  h.el("capture-jpg").checked=true;
  h.el("capture-raw").checked=false;
  h.el("capture-png").checked=false;
  h.el("sequence-count").value="5";
  h.el("sequence-count").dispatch("input");
  assert.equal(h.el("start-sequence").disabled,false);
  await h.el("start-sequence").dispatch("click");
  const sends=h.calls.filter(c=>c.url==="/api/capture/sequence");
  assert.equal(sends.length,1);
  assert.deepEqual(sends[0].payload,{count:5,formats:["fits","jpg"]});
  await h.intervals.get(50)();
  assert.equal(h.el("start-sequence").disabled,true);
  assert.equal(h.el("gain-5").disabled,true);
  assert.equal(h.el("cancel-sequence").disabled,false);
  h.updateCapture({phase:"saving",completed_frames:2,current_frame:3, total_frames:5});
  await h.intervals.get(50)();
  assert.match(h.el("sequence-progress").textContent,/2 \/ 5/);
  h.updateCapture({phase:"done",completed_frames:5,
    directories:["captures/a","captures/b","captures/c","captures/d","captures/e"]});
  await h.intervals.get(50)();
  assert.equal(h.el("start-sequence").disabled,false);
  assert.equal(h.el("cancel-sequence").disabled,true);
  assert.match(h.el("capture-results").textContent,/captures\/e/);
});

test("sequence cancel is operator controlled and updates browser status",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("cancel-sequence").disabled,true);
  await h.el("take-control").dispatch("click");
  h.el("sequence-count").value="2";
  h.el("capture-fits").checked=true;
  h.el("sequence-count").dispatch("input");
  await h.el("start-sequence").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,false);
  await h.el("cancel-sequence").dispatch("click");
  await h.intervals.get(50)();
  assert.equal(h.el("cancel-sequence").disabled,true);
  assert.match(h.el("capture-state").textContent,/cancelled/);
});

test("invalid sequence counts are rejected without POST",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  for(const count of ["1","101","3.5","0"]) {
    h.el("sequence-count").value=count;
    h.el("sequence-count").dispatch("input");
    assert.equal(h.el("start-sequence").disabled,true);
  }
  assert.equal(h.calls.filter(c=>c.url==="/api/capture/sequence").length,0);
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
  await h.intervals.get(2500)();
  assert.equal(h.el("mount-altitude").textContent,"—");
  assert.equal(h.el("mount-ra").textContent,"—");
  assert.match(h.el("mount-error").textContent,/Serial port disappeared/);
  assert.equal(h.el("mount-connect").disabled,false);
});

test("mount UI has only read-only connection actions, not motion controls",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../astropi/templates/index.html"),"utf8");
  assert.match(html,/id="mount-connect"/);
  assert.match(html,/id="mount-disconnect"/);
  assert.doesNotMatch(html,/id="mount-(?:home|goto|slew|track|park|east|west|north|south)"/);
});


test("motion buttons cannot command mount without operator and explicit arm",async()=>{
  const h=harness();
  await h.flush();
  assert.equal(h.el("mount-north").disabled,true);
  assert.equal(h.el("mount-stop").disabled,true);
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  assert.equal(h.el("mount-stop").disabled,false);
  assert.equal(h.el("mount-north").disabled,true);
  assert.equal(h.el("mount-arm").disabled,false);
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog").length,0);
  await h.el("mount-arm").dispatch("click");
  assert.equal(h.el("mount-east").disabled,false);
  await h.el("mount-east").dispatch("pointerdown");
  let requests=h.calls.filter(c=>c.url==="/api/mount/jog");
  assert.equal(requests.length,1);
  assert.equal(requests[0].payload.direction,"east");
  await h.intervals.get(150)();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/jog-heartbeat").length,1);
  h.documentEvent("pointerup");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  assert.equal(h.el("mount-east").disabled,true,
    "each jog requires a fresh explicit arm");
});

test("window blur and visibility change request Stop",async()=>{
  const h=harness();
  await h.flush();
  await h.el("take-control").dispatch("click");
  await h.el("mount-connect").dispatch("click");
  await h.el("mount-arm").dispatch("click");
  await h.el("mount-north").dispatch("pointerdown");
  h.windowEvent("blur");
  await h.flush();
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
  h.updateMount({motion_phase:"idle",motion_armed:false,stop_stable:true});
  await h.intervals.get(1000)();
  await h.el("mount-arm").dispatch("click");
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
  assert.equal(h.el("mount-arm").disabled,true);
  assert.equal(h.el("mount-stop").disabled,false);
  await h.el("mount-stop").dispatch("click");
  assert.equal(h.calls.filter(c=>c.url==="/api/mount/stop").length,1);
});
