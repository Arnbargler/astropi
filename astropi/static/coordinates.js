"use strict";
// Approximate geocentric J2000 catalogue RA/Dec -> local geometric Alt/Az.
// No atmospheric refraction, proper motion, telescope alignment, terrain,
// or mount mechanical limits. Intended for Find's planning display only.
(() => {
  const RAD = Math.PI / 180;
  const DEG = 180 / Math.PI;
  const norm = degrees => ((degrees % 360) + 360) % 360;

  function precessJ2000(raDeg, decDeg, centuries) {
    // IAU 1976 precession (Meeus, Astronomical Algorithms, ch. 21),
    // J2000.0 to mean equator/equinox of the observation date.
    // Angles zeta, z and theta are polynomials in arcseconds.
    const t = centuries, t2 = t * t, t3 = t2 * t;
    const zeta = (2306.2181*t + 0.30188*t2 + 0.017998*t3) / 3600 * RAD;
    const z = (2306.2181*t + 1.09468*t2 + 0.018203*t3) / 3600 * RAD;
    const theta = (2004.3109*t - 0.42665*t2 - 0.041833*t3) / 3600 * RAD;
    const ra = raDeg * RAD + zeta, dec = decDeg * RAD;
    const a = Math.cos(dec) * Math.sin(ra);
    const b = Math.cos(theta) * Math.cos(dec) * Math.cos(ra) -
              Math.sin(theta) * Math.sin(dec);
    const c = Math.sin(theta) * Math.cos(dec) * Math.cos(ra) +
              Math.cos(theta) * Math.sin(dec);
    return {
      raDeg: norm((Math.atan2(a, b) + z) * DEG),
      decDeg: Math.asin(Math.max(-1, Math.min(1, c))) * DEG
    };
  }

  function position(raDeg, decDeg, utc, latitudeDeg, longitudeEastDeg) {
    if (![raDeg, decDeg, latitudeDeg, longitudeEastDeg].every(Number.isFinite) ||
        raDeg < 0 || raDeg >= 360 || Math.abs(decDeg) > 90 ||
        Math.abs(latitudeDeg) > 90 || Math.abs(longitudeEastDeg) > 180 ||
        !(utc instanceof Date) || !Number.isFinite(utc.getTime()))
      throw new RangeError("Invalid catalogue coordinates, observing site or UTC");
    const jd = utc.getTime() / 86400000 + 2440587.5;
    const t = (jd - 2451545.0) / 36525;
    const mean = precessJ2000(raDeg, decDeg, t);
    // Mean Greenwich sidereal time in degrees, then local sidereal angle.
    const gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) +
                 0.000387933 * t*t - t*t*t / 38710000;
    const hourAngle = (norm(gmst + longitudeEastDeg - mean.raDeg)) * RAD;
    const dec = mean.decDeg * RAD, lat = latitudeDeg * RAD;
    // ENU unit vector: azimuth measured clockwise from true north.
    const east = -Math.cos(dec) * Math.sin(hourAngle);
    const north = Math.sin(dec) * Math.cos(lat) -
                  Math.cos(dec) * Math.cos(hourAngle) * Math.sin(lat);
    const up = Math.sin(dec) * Math.sin(lat) +
               Math.cos(dec) * Math.cos(hourAngle) * Math.cos(lat);
    return {
      altitudeDeg: Math.asin(Math.max(-1, Math.min(1, up))) * DEG,
      azimuthDeg: norm(Math.atan2(east, north) * DEG),
      meanRaDeg: mean.raDeg, meanDecDeg: mean.decDeg
    };
  }

  window.AstroPiCoordinates = Object.freeze({position, precessJ2000});
})();
