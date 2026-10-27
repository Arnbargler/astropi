# AstroPi Requirements

This document records features explicitly selected for AstroPi. The larger à-la-carte feature list is still under consideration; its other items have **not** been selected or specified here.

## Selected

### SKY-001 — Lightweight offline deep-sky atlas

**Selected solution:** VirtualSky as the browser-based sky-chart engine, with the locally stored OpenNGC catalogue providing roughly 14,000 NGC/IC deep-sky objects.

**Required behaviour:**
- Display a traditional schematic star chart rather than professional photographic sky-survey images.
- Mark galaxies, nebulae and star clusters using clear, conventional DSO symbols.
- Make the DSO catalogue searchable and allow object selection.
- Support passing a selected object's sky coordinates to AstroPi's GoTo controller once that controller is implemented.
- Work offline with bundled chart assets and catalogue data.
- Keep the atlas integration modular so the rendering engine can be replaced without rewriting the mount controller.

**Implementation / validation note:** Before relying on the integration, test VirtualSky with the full OpenNGC catalogue for rendering performance, label density and correct object selection. Filtering the objects displayed at each zoom level is acceptable; the full catalogue should remain searchable. The selection is recorded here; it is **not yet implemented or hardware-tested**.

## Explicit scope decisions

- **Camera:** SVBONY SV705C only. The SC571CC is **out of scope**; do not plan a ToupTek camera driver, camera switching, or SC571CC cooling controls.

## Not yet selected

Other items from the proposed à-la-carte feature list remain undecided unless explicitly recorded here. Do not interpret earlier discussion as approval to implement them.
