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
  const code = fs.readFileSync(path.join(root,"astropi/static/atlas.js"),"utf8");
  vm.runInNewContext(code,{
    window:fakeWindow, document:{getElementById:el,createElement:()=>({value:""})},
    fetch, performance:{now:()=>state.monotonic},setInterval:(fn,ms)=>{timers.push({fn,ms})},
    Date, Number, Map, Promise
  });
  return {state,el,requests,timers,api:fakeWindow.AstroPiAtlas,sky};
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
