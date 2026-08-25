const zlib = require('zlib');
const fs = require('fs');
const path = require('path');

// ---- PNG encoding -----------------------------------------------------------
const crcTable = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = -1;
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td), 0);
  return Buffer.concat([len, td, crc]);
}
function encodePNG(width, height, rgba) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;  // bit depth
  ihdr[9] = 6;  // colour type: RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// ---- signed distance field primitives (units: fraction of icon size) --------
const sdRoundRect = (px, py, cx, cy, hw, hh, r) => {
  const qx = Math.abs(px - cx) - (hw - r);
  const qy = Math.abs(py - cy) - (hh - r);
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
};
const sdRing = (px, py, cx, cy, radius, halfWidth) =>
  Math.abs(Math.hypot(px - cx, py - cy) - radius) - halfWidth;
const sdCapsule = (px, py, ax, ay, bx, by, r) => {
  const pax = px - ax, pay = py - ay, bax = bx - ax, bay = by - ay;
  const h = Math.min(1, Math.max(0, (pax * bax + pay * bay) / (bax * bax + bay * bay)));
  return Math.hypot(pax - bax * h, pay - bay * h) - r;
};
const smin = (a, b) => Math.min(a, b);

// "84" wordmark, centred in a 0..1 box, tuned by `scale` (glyph height fraction)
function glyphDistance(x, y, scale, CY) {
  const cy = CY;
  const h = scale;              // full glyph height
  const rr = h / 4;             // radius of each lobe of the 8
  const w = h * 0.115;          // stroke half-width
  const gx8 = 0.5 - h * 0.36;   // centre x of the 8
  const gx4 = 0.5 + h * 0.375;  // centre x of the 4

  // 8 — two stacked rings
  let d = smin(
    sdRing(x, y, gx8, cy - rr, rr, w),
    sdRing(x, y, gx8, cy + rr, rr, w)
  );

  // 4 — diagonal, crossbar, stem
  const top = cy - h / 2, bot = cy + h / 2;
  const barY = cy + h * 0.16;
  const stemX = gx4 + h * 0.10;
  const leftX = gx4 - h * 0.27;
  d = smin(d, sdCapsule(x, y, stemX, top, leftX, barY, w));
  d = smin(d, sdCapsule(x, y, leftX - w * 0.2, barY, gx4 + h * 0.30, barY, w));
  d = smin(d, sdCapsule(x, y, stemX, top, stemX, bot, w));
  return d;
}

// ---- renderer ---------------------------------------------------------------
const BG = [0x0e, 0x0f, 0x12];
const FG = [0xf5, 0xf5, 0xf4];
const ACCENT = [0x4a, 0xde, 0x80];

function render(size, opts = {}) {
  const { maskable = false, transparentOutside = false } = opts;
  // maskable icons must keep content inside the 80% safe zone
  const glyphScale = maskable ? 0.38 : 0.46;
  const cyG = 0.47;
  const plateRadius = maskable ? 0.5 : 0.22; // full-bleed circle-ish vs. squircle
  const plateHalf = maskable ? 0.5 : 0.5;
  const buf = Buffer.alloc(size * size * 4);
  const SS = 4;                    // supersampling factor per axis
  const px = 1 / size;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let plate = 0, glyph = 0, accent = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const u = (x + (sx + 0.5) / SS) / size;
          const v = (y + (sy + 0.5) / SS) / size;
          const dp = sdRoundRect(u, v, 0.5, 0.5, plateHalf, plateHalf, plateRadius);
          const dg = glyphDistance(u, v, glyphScale, cyG);
          // underline accent bar beneath the wordmark
          const da = sdCapsule(u, v, 0.5 - glyphScale * 0.46, cyG + glyphScale * 0.86,
                                     0.5 + glyphScale * 0.46, cyG + glyphScale * 0.86,
                                     glyphScale * 0.06);
          plate += dp <= 0 ? 1 : 0;
          glyph += dg <= 0 ? 1 : 0;
          accent += da <= 0 ? 1 : 0;
        }
      }
      const n = SS * SS;
      plate /= n; glyph /= n; accent /= n;

      let r = BG[0], g = BG[1], b = BG[2];
      let a = transparentOutside ? plate : 1;
      if (!transparentOutside) { r = BG[0]; g = BG[1]; b = BG[2]; }
      // composite accent then glyph over the plate
      const over = (base, top, cov) => base * (1 - cov) + top * cov;
      r = over(r, ACCENT[0], accent); g = over(g, ACCENT[1], accent); b = over(b, ACCENT[2], accent);
      r = over(r, FG[0], glyph);      g = over(g, FG[1], glyph);      b = over(b, FG[2], glyph);

      const i = (y * size + x) * 4;
      buf[i] = Math.round(r); buf[i + 1] = Math.round(g); buf[i + 2] = Math.round(b);
      buf[i + 3] = Math.round(a * 255);
    }
  }
  return encodePNG(size, size, buf);
}

const outDir = process.argv[2];
fs.mkdirSync(outDir, { recursive: true });
const jobs = [
  ['icon-192.png', 192, {}],
  ['icon-512.png', 512, {}],
  ['icon-maskable-512.png', 512, { maskable: true }],
  ['apple-touch-icon.png', 180, {}],
  ['favicon-32.png', 32, {}],
];
for (const [name, size, opts] of jobs) {
  fs.writeFileSync(path.join(outDir, name), render(size, opts));
  console.log('wrote', name, size + 'px');
}
