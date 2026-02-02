// Extracted from APK app-service.js to generate rt_draw packets
// Run with: node scripts/extract_rt_draw.js

// Helper functions
function bytes_write_int(arr, offset, value, num_bytes, big_endian = false) {
    for (let i = 0; i < num_bytes; i++) {
        const byte_offset = big_endian ? (num_bytes - 1 - i) : i;
        arr[offset + byte_offset] = (value >> (i * 8)) & 0xFF;
    }
}

function memcpy_buf(dest, dest_offset, src, src_offset, length) {
    for (let i = 0; i < length; i++) {
        dest[dest_offset + i] = src[src_offset + i];
    }
}

// ve function - wraps payload in YS protocol
function ve(sno, payload, flags, cmd_idx, checksum_flag) {
    const c = 10 + payload.length + 2; // header + payload + checksums
    let l, o;
    
    switch (checksum_flag) {
        case 1:
            l = new Uint8Array(2 + c);
            bytes_write_int(l, 0, c, 2);  // length prefix
            o = 2;  // data starts at offset 2
            break;
        case 0:
        default:
            l = new Uint8Array(c);
            o = 0;
            break;
    }
    
    // Write header starting at offset o
    bytes_write_int(l, o, 21930, 2, false);      // 0x55AA -> AA 55
    bytes_write_int(l, o + 2, 65535, 2, false);  // 0xFFFF -> FF FF
    bytes_write_int(l, o + 4, payload.length + 4, 2, false);  // inner length
    bytes_write_int(l, o + 6, sno & 0xFFFF, 2, false);  // sequence number
    l[o + 8] = flags;  // flags
    l[o + 9] = cmd_idx;  // command index
    
    // Copy payload
    memcpy_buf(l, o + 10, payload, 0, payload.length);
    
    // Calculate checksum if enabled
    if (checksum_flag) {
        let p = 0;
        const checksum_end = c + o - 2;
        for (let f = o; f < checksum_end; f++) {
            p += l[f];
        }
        bytes_write_int(l, l.length - 2, p, 2);
    }
    
    return l;
}

// Build rt_draw type 1 (fill rect) payload
function build_rt_draw_rect(color, type_rect, x0, y0, x1, y1) {
    const t = new Uint8Array(15);
    t[0] = 50;  // TLV tag
    t[1] = 13;  // TLV length
    t[2] = 1;   // type = 1 (fill rect)
    bytes_write_int(t, 3, color, 3, false);  // color (3 bytes LE)
    t[6] = type_rect;  // type_rect (0 = fill)
    bytes_write_int(t, 7, x0, 2, false);
    bytes_write_int(t, 9, y0, 2, false);
    bytes_write_int(t, 11, x1, 2, false);
    bytes_write_int(t, 13, y1, 2, false);
    return t;
}

// Build complete rt_draw packet
function build_rt_draw_packet(sno, color, x0, y0, x1, y1) {
    const payload = build_rt_draw_rect(color, 0, x0, y0, x1, y1);
    // ye function sets w=2 and calls ve(sno, payload, 193, w, 1)
    return ve(sno, payload, 193, 2, 1);
}

// Test cases
console.log("=== RT_DRAW PACKET GENERATION ===\n");

// Clear screen (black rect covering full display)
const clear_packet = build_rt_draw_packet(2, 0x000000, 0, 0, 95, 127);
console.log("CLEAR SCREEN (black 96x128):");
console.log("Hex:", Buffer.from(clear_packet).toString('hex'));
console.log("Bytes:", Array.from(clear_packet).map(b => b.toString(16).padStart(2, '0')).join(' '));
console.log("Length:", clear_packet.length);
console.log();

// Red rectangle (30,40) to (65,87)
// Color: red = 0xFF (R=255, G=0, B=0) in R + G<<8 + B<<16 format
const red_color = 255;  // Just red
const red_rect = build_rt_draw_packet(3, red_color, 30, 40, 65, 87);
console.log("RED RECTANGLE (30,40)-(65,87):");
console.log("Hex:", Buffer.from(red_rect).toString('hex'));
console.log("Bytes:", Array.from(red_rect).map(b => b.toString(16).padStart(2, '0')).join(' '));
console.log("Length:", red_rect.length);
console.log();

// Green rectangle
const green_color = 255 << 8;  // G=255
const green_rect = build_rt_draw_packet(4, green_color, 10, 10, 30, 30);
console.log("GREEN RECTANGLE (10,10)-(30,30):");
console.log("Hex:", Buffer.from(green_rect).toString('hex'));
console.log("Bytes:", Array.from(green_rect).map(b => b.toString(16).padStart(2, '0')).join(' '));
console.log("Length:", green_rect.length);
