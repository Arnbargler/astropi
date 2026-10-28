# Bundled VirtualSky files (offline, pinned)

Source: https://github.com/slowe/VirtualSky
Upstream revision/tree: `271c801d6504d1c478bc0c64dce4938399749c69`
VirtualSky application version: **0.7.7** (reported in `virtualsky.js`).
Original author: Stuart Lowe / Las Cumbres Observatory Global Telescope.
These seven files are copied unmodified from the upstream revision:
`stuquery.min.js`, `virtualsky.min.js`, `virtualsky-planets.js`,
`stars.json`, `lines_latin.json`, `lang/en.json`, `messier.json`.

Upstream's [site](https://github.com/slowe/VirtualSky/blob/gh-pages/index.html)
states the project is provided freely for **educational and non-profit use**.
Upstream does **not** supply a standalone SPDX/open-source LICENSE file.
Do not assume commercial redistribution or sublicensing rights. Preserve
the original attribution and review permissions before wider distribution.

No CDN, remote ephemeris, location service or image tiles are used at runtime.
VirtualSky's built-in object-name lookup and default Wikisky marker
HTML are intentionally bypassed by `atlas.js` with local JSON + text-only
pointer HTML. The local planet ephemeris helper is loaded rather than the
dated `planets.json` file. Other upstream optional assets are not needed.
