// Limit the entire data URL, including base64 overhead. Keep small originals at
// their native resolution; reduce JPEG quality before sacrificing more pixels.
export async function labelPhoto(file: File, count: number): Promise<string> {
  // The backend also caps the batch at 1.5 MiB decoded (2 MiB base64).
  const maxLength = Math.min(1024 ** 2, Math.floor(2 * 1024 ** 2 / count))
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
