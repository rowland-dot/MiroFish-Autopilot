// TDD: parse the server's Content-Disposition filename for downloads.
// Prefers RFC5987 filename* (UTF-8, holds Chinese), falls back to plain
// filename=, then to the caller's fallback.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { filenameFromDisposition } from '../src/utils/downloadName.js'

test('decodes RFC5987 filename* with Chinese', () => {
  const cd = `attachment; filename="report_x.docx"; filename*=UTF-8''report_%E7%88%86%E6%AC%BE%E8%AF%A6%E6%83%85%E9%A1%B5.docx`
  assert.equal(filenameFromDisposition(cd, 'fb.docx'), 'report_爆款详情页.docx')
})

test('falls back to plain filename= when no filename*', () => {
  assert.equal(filenameFromDisposition('attachment; filename="report_abc.md"', 'fb.md'), 'report_abc.md')
})

test('uses fallback when header missing or unparseable', () => {
  assert.equal(filenameFromDisposition('', 'fb.docx'), 'fb.docx')
  assert.equal(filenameFromDisposition(null, 'fb.docx'), 'fb.docx')
  assert.equal(filenameFromDisposition('attachment', 'fb.docx'), 'fb.docx')
})
