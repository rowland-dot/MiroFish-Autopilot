// Base64 <-> File, isolated so the pipeline store stays focused.
// Browser + Node-safe (btoa/atob in browser, Buffer under node --test).

export async function fileToB64(file) {
  const buf = new Uint8Array(await file.arrayBuffer())
  let bin = ''
  for (let i = 0; i < buf.length; i++) bin += String.fromCharCode(buf[i])
  const b64 = (typeof btoa === 'function') ? btoa(bin) : Buffer.from(buf).toString('base64')
  return { b64, name: file.name, type: file.type || '' }
}

export function b64ToFile({ b64, name, type }) {
  const bin = (typeof atob === 'function') ? atob(b64) : Buffer.from(b64, 'base64').toString('binary')
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new File([bytes], name, { type })
}
