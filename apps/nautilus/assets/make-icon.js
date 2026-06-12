'use strict';
// Dev utility: generates the base64 PNG embedded in tray-icon.js.
// Run: node assets/make-icon.js
const zlib = require('node:zlib');

const SIZE = 16;
const rows = [];
for (let y = 0; y < SIZE; y++) {
  const row = [0]; // filter byte
  for (let x = 0; x < SIZE; x++) {
    const dx = x - 7.5;
    const dy = y - 7.5;
    const d = Math.sqrt(dx * dx + dy * dy);
    const inside = d <= 7;
    const ring = d > 4.2 && d <= 6.2;
    // purple disc with a lighter ring — reads as a "search" dot in the tray
    if (inside) {
      if (ring) row.push(0xc9, 0xb8, 0xff, 255);
      else row.push(0x7c, 0x5c, 0xff, 255);
    } else {
      row.push(0, 0, 0, 0);
    }
  }
  rows.push(Buffer.from(row));
}
const raw = Buffer.concat(rows);

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(zlib.crc32(body) >>> 0);
  return Buffer.concat([len, body, crc]);
}

const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(SIZE, 0);
ihdr.writeUInt32BE(SIZE, 4);
ihdr[8] = 8; // bit depth
ihdr[9] = 6; // RGBA
const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', zlib.deflateSync(raw)),
  chunk('IEND', Buffer.alloc(0)),
]);

console.log(png.toString('base64'));
