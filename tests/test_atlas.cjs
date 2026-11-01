"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const entries = JSON.parse(fs.readFileSync(
  path.join(root, "astropi/static/vendor/virtualsky/messier.json"), "utf8"));

function harness({clockAvailable=true}={}) {
  const elems = new Map(), requests = [], timers = [];
  const state = {monotonic: 1200, sky: null, options: null};
  function el(id) {
    if (!elems.has(id)) {
      elems.set(id, {id, value:"", textContent:"", handlers:{}, children:[],
        addEventListener(name,cb){this.handlers[name]=cb;},
        dispatch(name,event={}){return this.handlers[name](event);},
        appendChild(child){this.children.push(child);return child;}});
    }
    return elems.get(id);
  }
  const sky = {
    pointers:[], projection:{id:"polar"}, constellation:{lines:true,labels:true},
    grid:{eq:false},times:{LST:6},clock:null,resizeCount:0,drawCount:0,
    addPointer(p){this.pointers.push(p);return this.pointers.length;},
    setClock(d){this.clock=d;return this;},
    selectProjection(id){this.projection.id=id;return this;},
    setFOV(value){this.fov=value;return this;},
    setRADec(ra,dec){this.center={ra,dec};return this;},
    changeFOV(delta){this.fov += delta > 0 ? -2 : 2;return this;},
    draw(){this.drawCount++;return this;},
    resize(){this.resizeCount++;return this;},
    checkLoaded(){return this;}
  };
  const fakeWindow = {
    S:{virtualsky(options){state.options=options;state.sky=sky;return sky;}},
    addEventListener(){},requestAnimationFrame(fn){fn();}
  };
  const fetch = async (url) => {
    requests.push(url);
    if(url==="/api/status") {
      if(!clockAvailable) throw Error("offline Pi");
      return {ok:true,json:async()=>({utc:"2026-10-28T15:40:00+00:00"})};
    }
    if(url==="/static/vendor/virtualsky/messier.json")
      return {ok:true,json:async()=>entries};
    throw Error("Unexpected or online URL: "+url);
  };
  const coordinatesCode = fs.readFileSync(path.join(root,"astropi/static/coordinates.js"),"utf8");
  vm.runInNewContext(coordinatesCode,{window:fakeWindow,Date,Number,Math,RangeError,Object});
  const code = fs.readFileSync(path.join(root,"astropi/static/atlas.js"),"utf8");
  vm.runInNewContext(code,{
    window:fakeWindow, document:{getElementById:el,createElement:()=>({value:""})},
    fetch, performance:{now:()=>state.monotonic},setInterval:(fn,ms)=>{timers.push({fn,ms})},
    Date, Number, Map, Promise
  });
  return {state,el,requests,timers,api:fakeWindow.AstroPiAtlas,coordinates:fakeWindow.AstroPiCoordinates,sky};
}

test("opens local atlas from Pi UTC, fixed site and all 110 text-only pointers",async()=>{
  const h=harness();
  await h.api.show();
  assert.deepEqual(h.requests,[
    "/api/status","/static/vendor/virtualsky/messier.json"
  ]);
  assert.equal(h.state.options.latitude,45.2933);
  assert.equal(h.state.options.longitude,-75.8571);
  assert.equal(h.state.options.projection,"polar");
  assert.equal(h.state.options.keyboard,false);
  assert.equal(h.sky.pointers.length,110);
  assert.ok(h.sky.pointers.every(p=>!p.html.includes("<img")&&!p.html.includes("http")));
  assert.equal(h.sky.clock.toISOString(),"2026-10-28T15:40:00.000Z");
  assert.equal(h.el("atlas-messier-options").children.length,110);
  assert.ok(h.sky.resizeCount>0);
  h.state.monotonic+=5000;
  h.timers.find(t=>t.ms===1000).fn();
  assert.equal(h.sky.clock.toISOString(),"2026-10-28T15:40:05.000Z");
});

test("search and clicked marker centre detail only; horizon/zoom/grid work",async()=>{
  const h=harness();
  await h.api.show();
  h.el("atlas-search").value="m 031";
  h.el("atlas-search-form").dispatch("submit",{preventDefault(){}});
  const m31=entries.find(o=>o.target.name==="M31");
  assert.equal(h.sky.center.ra,m31.ra.decimal);
  assert.equal(h.sky.center.dec,m31.dec.decimal);
  assert.equal(h.sky.projection.id,"gnomic");
  assert.match(h.el("atlas-selection").textContent,/M31 · RA/);
  assert.match(h.el("atlas-status").textContent,/mount unchanged/);
  h.state.options.callback.click({matched:0});
  assert.equal(h.el("atlas-search").value,"M1");
  h.el("atlas-allsky").dispatch("click");
  assert.equal(h.sky.projection.id,"polar");
  h.el("atlas-zoom-in").dispatch("click");
  assert.equal(h.sky.projection.id,"gnomic");
  h.el("atlas-grid").dispatch("change",{target:{checked:true}});
  assert.equal(h.sky.grid.eq,true);
  h.el("atlas-constellations").dispatch("change",{target:{checked:false}});
  assert.equal(h.sky.constellation.lines,false);
  assert.equal(h.sky.constellation.labels,false);
  h.el("atlas-search").value="M111";
  h.el("atlas-search-form").dispatch("submit",{preventDefault(){}});
  assert.match(h.el("atlas-status").textContent,/No Messier match/);
  assert.ok(h.requests.every(url=>url.startsWith("/api/status")||url.startsWith("/static/vendor/")));
});

test("without Pi UTC atlas waits rather than substituting browser time",async()=>{
  const h=harness({clockAvailable:false});
  await h.api.show();
  assert.equal(h.state.sky,null);
  assert.match(h.el("atlas-status").textContent,/Waiting for the Pi/);
  h.api.syncUTC("2026-10-28T16:00:00Z");
  // asynchronous catalogue boot is triggered by the resumed Pi UTC poll
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.sky.pointers.length,110);
  assert.equal(h.sky.clock.toISOString(),"2026-10-28T16:00:00.000Z");
  h.api.hide();
  const last=h.sky.clock.toISOString();
  h.api.syncUTC("2026-10-28T16:01:00Z");
  assert.equal(h.sky.clock.toISOString(),last);
});

test("J2000 to local geometric Alt/Az: zenith, east, west, below horizon",()=>{
  const {position,precessJ2000}=harness().coordinates;
  const utc=new Date("2000-01-01T12:00:00.000Z");
  const gmst=280.46061837;
  const at=(ra,dec,lat=0,lon=0)=>position((ra+360)%360,dec,utc,lat,lon);
  assert.ok(Math.abs(at(gmst,0).altitudeDeg-90)<0.0001);
  const east=at(gmst+90,0);
  assert.ok(Math.abs(east.altitudeDeg)<0.0001);
  assert.ok(Math.abs(east.azimuthDeg-90)<0.0001);
  const west=at(gmst-90,0);
  assert.ok(Math.abs(west.altitudeDeg)<0.0001);
  assert.ok(Math.abs(west.azimuthDeg-270)<0.0001);
  const north=at(gmst,30);
  assert.ok(Math.abs(north.altitudeDeg-60)<0.0001);
  assert.ok(Math.min(north.azimuthDeg,360-north.azimuthDeg)<0.0001);
  assert.ok(Math.abs(at(gmst+180,0).altitudeDeg+90)<0.0001);
  const southern=at(gmst,0,45);
  assert.ok(Math.abs(southern.altitudeDeg-45)<0.0001);
  assert.ok(Math.abs(southern.azimuthDeg-180)<0.0001);
  const future=precessJ2000(0,0,0.5);
  assert.ok(future.raDeg>0.63 && future.raDeg<0.65);
  assert.ok(future.decDeg>0.27 && future.decDeg<0.29);
  assert.throws(()=>position(360,0,utc,45,-75),RangeError);
  assert.throws(()=>position(0,91,utc,45,-75),RangeError);
  assert.throws(()=>position(0,0,new Date("invalid"),45,-75),RangeError);
});

test("selected Messier target shows updated geometric visibility from Pi UTC only",async()=>{
  const h=harness();
  await h.api.show();
  assert.notEqual(h.el("atlas-target-readout").hidden,false);
  h.el("atlas-search").value="M42";
  h.el("atlas-search-form").dispatch("submit",{preventDefault(){}});
  assert.equal(h.el("atlas-target-readout").hidden,false);
  const target=entries.find(item=>item.target.name==="M42");
  const pos=h.coordinates.position(
    target.ra.decimal,target.dec.decimal,new Date("2026-10-28T15:40:00Z"),
    45.2933,-75.8571);
  assert.equal(h.el("atlas-altitude").textContent,pos.altitudeDeg.toFixed(1)+"°");
  assert.equal(h.el("atlas-azimuth").textContent,pos.azimuthDeg.toFixed(1)+"°");
  assert.equal(h.el("atlas-visibility").textContent,pos.altitudeDeg>=0
    ? "Above geometric horizon" : "Below geometric horizon");
  const oldAltitude=h.el("atlas-altitude").textContent;
  h.state.monotonic+=3600000;
  h.timers.find(t=>t.ms===1000).fn();
  assert.notEqual(h.el("atlas-altitude").textContent,oldAltitude);
  assert.equal(h.el("atlas-search").value,"M42");
  assert.ok(h.requests.every(url=>!url.startsWith("/api/mount/")));
});
