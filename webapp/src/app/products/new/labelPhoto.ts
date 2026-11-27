// Read only a bounded prefix. A small compressed file can still expand into
// a very large bitmap; checking dimensions after createImageBitmap is too late.
function sourceDimensions(header: DataView): [number, number] {
  if (header.getUint32(0) === 0x89504e47 && header.getUint32(4) === 0x0d0a1a0a &&
      header.getUint32(8) === 13 && header.getUint32(12) === 0x49484452) {
    return [header.getUint32(16), header.getUint32(20)] // PNG IHDR
  }
  if (header.getUint16(0) === 0xffd8) {
    let offset = 2
    while (header.getUint8(offset++) === 0xff) {
      let marker = header.getUint8(offset++)
      while (marker === 0xff) marker = header.getUint8(offset++) // padding
      const length = header.getUint16(offset)
      if (length < 2) break
      if ([0xc0, 0xc1, 0xc2].includes(marker)) { // sequential or progressive JPEG
        return [header.getUint16(offset + 5), header.getUint16(offset + 3)]
      }
      // Skip only metadata and tables. Never search compressed image data for a frame.
      if (!(marker >= 0xe0 && marker <= 0xef) && ![0xfe, 0xdb, 0xc4, 0xdd].includes(marker)) break
      offset += length
    }
  }
  throw new Error('Unknown source dimensions')
}

// Limit the entire data URL, including base64 overhead. Keep small originals at
// their native resolution; reduce JPEG quality before sacrificing more pixels.
export async function labelPhoto(file: File, count: number): Promise<string> {
  // The backend also caps the batch at 1.5 MiB decoded (2 MiB base64).
  const maxLength = Math.min(1024 ** 2, Math.floor(2 * 1024 ** 2 / count))
  if (file.size > 16 * 1024 ** 2) throw new Error('Source file too large')
  const [width, height] = sourceDimensions(new DataView(await file.slice(0, 256 * 1024).arrayBuffer()))
  if (!width || !height || Math.max(width, height) > 8192 || width * height > 24_000_000) {
    throw new Error('Source dimensions too large or missing')
  }
  const bitmap = await createImageBitmap(file)
  try {
    const canvas = document.createElement('canvas')
    const longest = Math.max(bitmap.width, bitmap.height)
    for (let edge = Math.min(longest, 2560); ; edge = Math.floor(edge * 0.8)) {
      canvas.width = Math.max(1, Math.round(bitmap.width * edge / longest))
      canvas.height = Math.max(1, Math.round(bitmap.height * edge / longest))
      const context = canvas.getContext('2d', { alpha: false })
      if (!context) throw new Error('Image conversion unavailable')
      context.fillStyle = 'white'
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      for (const quality of [0.92, 0.82, 0.72]) {
        const url = canvas.toDataURL('image/jpeg', quality)
        if (url.startsWith('data:image/jpeg;base64,') && url.length <= maxLength) return url
      }
      if (edge <= 1000) throw new Error('Cannot fit a readable photo')
    }
  } finally {
    bitmap.close()
  }
}
