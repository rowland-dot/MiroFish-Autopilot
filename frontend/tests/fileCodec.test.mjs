import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fileToB64, b64ToFile } from '../src/store/fileCodec.js'

test('round-trips a file through base64', async () => {
  const original = new File([new Uint8Array([1, 2, 3, 4])], 'x.docx', { type: 'application/docx' })
  const enc = await fileToB64(original)
  assert.equal(typeof enc.b64, 'string')
  assert.equal(enc.name, 'x.docx')
  assert.equal(enc.type, 'application/docx')
  const back = b64ToFile(enc)
  assert.equal(back.name, 'x.docx')
  assert.equal(back.size, 4)
})
