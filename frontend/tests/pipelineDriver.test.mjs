import { test } from 'node:test'
import assert from 'node:assert/strict'
import { runOne } from '../src/services/pipelineDriver.js'

function mockApi(calls) {
  return {
    generateOntology: async () => (calls.push('ontology'), { data: { project_id: 'proj_1' } }),
    buildGraph: async () => (calls.push('build'), { data: { reused: true, graph_id: 'g1' } }),
    getTaskStatus: async () => ({ data: { status: 'completed' } }),
    getProject: async () => ({ data: { graph_id: 'g1' } }),
    createSimulation: async () => (calls.push('create'), { data: { simulation_id: 'sim_1' } }),
    prepareSimulation: async () => (calls.push('prepare'), { data: { task_id: 'pt1' } }),
    getPrepareStatus: async () => ({ data: { status: 'completed' } }),
    startSimulation: async () => (calls.push('start'), { data: { runner_status: 'running' } }),
    // realistic: idle before start (resume pre-check), live for a poll, then finishes
    getRunStatus: (() => { let n = 0; const seq = ['idle', 'running']; return async () => ({ data: { runner_status: seq[n++] || 'completed' } }) })(),
    getSystemStatus: async () => ({ data: { running_simulations: ['sim_1'] } }),
    generateReport: async () => (calls.push('report'), { data: { report_id: 'rep_1' } }),
  }
}
// non-reused build path: buildGraph returns a task -> poll -> getProject
function mockApiPolling(calls) {
  return { ...mockApi(calls),
    buildGraph: async () => (calls.push('build'), { data: { task_id: 'bt1' } }) }
}

function deps(api) {
  const rec = { sid: null, statuses: [] }
  return {
    api,
    store: { setStatus(_id, s) { rec.statuses.push(s) }, setSimId(_id, sid) { rec.sid = sid }, patch() {} },
    sleep: async () => {}, signal: () => {}, buildFormData: () => ({}),
    _rec: rec,
  }
}

test('runOne advances through the full sequence and backfills sim id', async () => {
  const calls = []
  const d = deps(mockApi(calls))
  await runOne({ _tmpId: 't1', file: {}, prompt: 'p' }, d)
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start', 'report'])
  assert.equal(d._rec.sid, 'sim_1')                                  // backfilled
  assert.deepEqual(d._rec.statuses, ['building', 'creating', 'preparing', 'running', 'reporting', 'done'])
  // 'running' must come AFTER the start call — marking it earlier let the
  // server-side reconcile delete the card mid-pipeline.
  assert.ok(d._rec.statuses.indexOf('running') > 0)
})

test('runOne polls the non-reused build task + prepare task', async () => {
  const calls = []
  await runOne({ _tmpId: 't2', file: {}, prompt: 'p' }, deps(mockApiPolling(calls)))
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start', 'report'])
})

test('a second tick does not re-enter runOne for an in-flight entry', async () => {
  const calls = []
  const api = mockApi(calls)
  let resolveOnto
  api.generateOntology = () => new Promise(r => { calls.push('ontology'); resolveOnto = () => r({ data: { project_id: 'proj_1' } }) })
  const inFlight = new Set()
  const entry = { _tmpId: 't3', mode: 'auto', file: {}, prompt: 'p' }
  const d = deps(api)
  const p1 = runOne(entry, d, inFlight)   // enters, adds t3, awaits ontology
  const p2 = runOne(entry, d, inFlight)   // must no-op (t3 already in flight)
  resolveOnto()
  await Promise.all([p1, p2])
  assert.equal(calls.filter(c => c === 'ontology').length, 1)
})

test('runOne resumes from create when graphId already present (no rebuild)', async () => {
  const calls = []
  await runOne({ _tmpId: 't4', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1' }, deps(mockApi(calls)))
  assert.deepEqual(calls, ['create', 'prepare', 'start', 'report'])   // skipped ontology + build
})

// 恢复保护：刷新浏览器后 runOne 重入，绝不能 force 重启一个已完成/在跑的模拟
test('resume on a COMPLETED run never calls start (no force-restart wipe)', async () => {
  const calls = []
  const api = mockApi(calls)
  api.getRunStatus = async () => ({ data: { runner_status: 'completed' } })
  const d = deps(api)
  await runOne({ _tmpId: 'r1', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1', realSimId: 'sim_1', status: 'running' }, d)
  assert.ok(!calls.includes('start'), 'must NOT restart a completed run')
  assert.ok(calls.includes('report'))
  assert.deepEqual(d._rec.statuses, ['reporting', 'done'])
})

test('resume on a LIVE run skips start and just polls to completion', async () => {
  const calls = []
  const api = mockApi(calls)
  let n = 0
  api.getRunStatus = async () => ({ data: { runner_status: n++ < 2 ? 'running' : 'completed' } })
  const d = deps(api)
  await runOne({ _tmpId: 'r2', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1', realSimId: 'sim_1', status: 'running' }, d)
  assert.ok(!calls.includes('start'), 'must NOT re-start a live run')
  assert.ok(d._rec.statuses.includes('running'))
  assert.ok(calls.includes('report'))
})

test('resume with an existing reportId never regenerates the report', async () => {
  const calls = []
  const api = mockApi(calls)
  api.getRunStatus = async () => ({ data: { runner_status: 'completed' } })
  const d = deps(api)
  await runOne({ _tmpId: 'r3', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1', realSimId: 'sim_1', reportId: 'rep_1', status: 'reporting' }, d)
  assert.ok(!calls.includes('report'), 'must NOT regenerate an existing report')
  assert.deepEqual(d._rec.statuses, ['reporting', 'done'])
})

test('build task failure fails the entry instead of spinning forever', async () => {
  const calls = []
  const api = mockApiPolling(calls)
  api.getTaskStatus = async () => ({ data: { status: 'failed', error: 'boom' } })
  const d = deps(api)
  await runOne({ _tmpId: 'r4', file: {}, prompt: 'p' }, d)
  assert.equal(d._rec.statuses.at(-1), 'failed')
  assert.ok(!calls.includes('create'), 'must stop at the failed build')
})

test('prepare task failure fails the entry instead of spinning forever', async () => {
  const calls = []
  const api = mockApi(calls)
  api.getPrepareStatus = async () => ({ data: { status: 'failed', error: 'boom' } })
  const d = deps(api)
  await runOne({ _tmpId: 'r5', file: {}, prompt: 'p' }, d)
  assert.equal(d._rec.statuses.at(-1), 'failed')
  assert.ok(!calls.includes('start'), 'must stop at the failed prepare')
})

// 瞬时限流（HTTP 429 / 网络抖动）不应整单失败 —— 应退避重试
test('transient 429 on ontology is retried, job survives', async () => {
  const calls = []
  const api = mockApi(calls)
  let n = 0
  api.generateOntology = async () => {
    calls.push('ontology')
    if (n++ === 0) { const e = new Error('LLM provider request failed (HTTP 429)'); throw e }
    return { data: { project_id: 'proj_1' } }
  }
  const d = deps(api)
  await runOne({ _tmpId: 'r6', file: {}, prompt: 'p' }, d)
  assert.equal(calls.filter(c => c === 'ontology').length, 2)
  assert.equal(d._rec.statuses.at(-1), 'done')
})

test('persistent failure records the error message on the entry', async () => {
  const calls = []
  const api = mockApi(calls)
  api.generateOntology = async () => { throw new Error('LLM provider request failed (HTTP 429)') }
  const patches = []
  const d = deps(api)
  d.store.patch = (_id, p) => patches.push(p)
  await runOne({ _tmpId: 'r7', file: {}, prompt: 'p' }, d)
  assert.equal(d._rec.statuses.at(-1), 'failed')
  assert.ok(patches.some(p => /HTTP 429/.test(p.error || '')), 'error message must be stored on the entry')
})

// 上传内容必须来自确定性的 b64 字节；无字节时绝不能发出「无文件」请求
test('buildFormData builds from fileB64 and throws when no bytes exist', async () => {
  const { buildFormData } = await import('../src/services/pipelineDriver.js')
  const fd = buildFormData({ fileB64: 'AQID', fileName: 'x.docx', fileType: '', prompt: 'p' })
  const f = fd.get('files')
  assert.equal(f.name, 'x.docx')
  assert.equal(f.size, 3)
  assert.throws(() => buildFormData({ prompt: 'p', fileName: 'x.docx' }), /文件/)
})

test('exhausted retries keep the root-cause error, not just the last attempt', async () => {
  const calls = []
  const api = mockApi(calls)
  let n = 0
  api.generateOntology = async () => {
    n++
    if (n < 3) throw new Error('LLM provider request failed (HTTP 429)')
    throw new Error('请至少上传一个文件')
  }
  const patches = []
  const d = deps(api)
  d.store.patch = (_id, p) => patches.push(p)
  await runOne({ _tmpId: 'r8', fileB64: 'AQID', fileName: 'x.docx', prompt: 'p' }, d)
  const err = (patches.find(p => p.error) || {}).error || ''
  assert.ok(/HTTP 429/.test(err), 'root-cause 429 must appear in the stored error: ' + err)
})

// 取消竞态：排队条目被出队开跑后用户点了取消——驱动器必须在阶段边界发现
// 条目已被删除并停手，否则被取消的任务会继续烧 ontology/build/prepare 的 LLM 配额
test('runOne aborts at the next stage boundary after its entry is cancelled', async () => {
  const calls = []
  const api = mockApi(calls)
  const d = deps(api)
  let cancelled = false
  api.generateOntology = async () => { calls.push('ontology'); cancelled = true; return { data: { project_id: 'proj_1' } } }
  d.store.raw = () => ({ entries: cancelled ? [] : [{ _tmpId: 'c1' }] })
  await runOne({ _tmpId: 'c1', file: {}, prompt: 'p' }, d)
  assert.ok(calls.includes('ontology'))
  assert.ok(!calls.includes('build'), 'must stop after cancellation')
  assert.ok(!calls.includes('create'))
})

test('plan-quota 429 (Token Plan limit) is NOT retried — fail fast with the real error', async () => {
  const calls = []
  const api = mockApi(calls)
  api.generateOntology = async () => {
    calls.push('ontology')
    throw new Error("已达到 Token Plan 速率限制，请升级 Token Plan 套餐或切换为按量付费 API 使用。 (2062)")
  }
  const d = deps(api)
  await runOne({ _tmpId: 'q1', file: {}, prompt: 'p' }, d)
  assert.equal(calls.filter(c => c === 'ontology').length, 1, 'quota exhaustion does not heal in seconds — no retry hammering')
  assert.equal(d._rec.statuses.at(-1), 'failed')
})

// 复用图谱：同文件+同提示词重复提交时跳过 ontology+建图（省 Zep 与时间）
test('identical resubmit reuses the existing completed graph (no ontology/build)', async () => {
  const calls = []
  const api = mockApi(calls)
  api.listProjects = async () => ({ data: [
    { project_id: 'proj_old', status: 'graph_completed', graph_id: 'g_old',
      simulation_requirement: 'p', files: [{ filename: 'x.docx' }], created_at: '2026-07-30T01:00:00' },
    { project_id: 'proj_other', status: 'graph_completed', graph_id: 'g_other',
      simulation_requirement: 'DIFFERENT', files: [{ filename: 'x.docx' }], created_at: '2026-07-31T01:00:00' },
  ] })
  const d = deps(api)
  await runOne({ _tmpId: 'g1', file: {}, prompt: 'p', fileName: 'x.docx' }, d)
  assert.ok(!calls.includes('ontology'), 'must reuse, not regenerate ontology')
  assert.ok(!calls.includes('build'))
  assert.ok(calls.includes('create'))
  assert.equal(d._rec.statuses.at(-1), 'done')
})

test('no matching project -> normal full pipeline; listProjects failure is non-fatal', async () => {
  const calls = []
  const api = mockApi(calls)
  api.listProjects = async () => { throw new Error('offline') }
  await runOne({ _tmpId: 'g2', file: {}, prompt: 'p', fileName: 'x.docx' }, deps(api))
  assert.ok(calls.includes('ontology'))
  assert.ok(calls.includes('build'))
})

// 建图接口对新建图谱同时返回 graph_id + task_id（Zep 异步处理 episode）。
// 只见 graph_id 就抢跑会拿着空图谱去 prepare -> 「没有找到符合条件的实体」
test('fresh build with BOTH graph_id and task_id waits for the task (no empty-graph race)', async () => {
  const calls = []
  const api = mockApi(calls)
  api.buildGraph = async () => (calls.push('build'), { data: { graph_id: 'g_new', task_id: 'bt9' } })
  let polls = 0
  api.getTaskStatus = async () => ({ data: { status: ++polls < 2 ? 'processing' : 'completed' } })
  const d = deps(api)
  await runOne({ _tmpId: 'z1', file: {}, prompt: 'p' }, d)
  assert.ok(polls >= 2, 'must poll the build task to completion before creating the sim')
  assert.equal(d._rec.statuses.at(-1), 'done')
})

test('reused graph still short-circuits without polling', async () => {
  const calls = []
  const api = mockApi(calls)   // buildGraph mock: { reused: true, graph_id: 'g1' }
  let polls = 0
  api.getTaskStatus = async () => { polls++; return { data: { status: 'completed' } } }
  await runOne({ _tmpId: 'z2', file: {}, prompt: 'p' }, deps(api))
  assert.equal(polls, 0, 'reused graph needs no task wait')
})

// 根因修正：OASIS 子进程在轮次跑完后「故意不退出」，等待 interview 命令
// （上游持久化设计）。自动流程必须：轮次完成 -> 就地生成报告（进程活着，
// interview 工具才有效）-> 报告完成后主动 stop 释放槽位。
// 生命周期契约（2026-08-04 实机验证）：后端拒绝在 run 非终态时生成报告，
// 而持久化子进程会永远停在 running。因此必须 close-env 转终态后再报告；
// 「报告期间活体采访」在后端 gate 下不可能，此前的假设是错的。
test('rounds-complete on a held-open process: close-env, wait terminal, then report', async () => {
  const calls = []
  const api = mockApi(calls)
  let closed = false
  api.getRunStatus = async () => ({ data: {
    runner_status: closed ? 'completed' : 'running',
    current_round: 72, total_rounds: 72,
    twitter_completed: true, reddit_completed: true } })
  api.closeSimulationEnv = async () => { calls.push('close-env'); closed = true; return { data: {} } }
  api.stopSimulation = async () => { calls.push('stop'); return { data: {} } }
  const d = deps(api)
  await runOne({ _tmpId: 'h1', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1', realSimId: 'sim_1', status: 'running' }, d)
  assert.ok(calls.includes('close-env'), 'held-open env must be closed first')
  assert.ok(calls.indexOf('close-env') < calls.indexOf('report'),
    'report is only accepted once the run is terminal')
  assert.equal(d._rec.statuses.at(-1), 'done')
})

test('normal terminal run still reports without needing a stop call', async () => {
  const calls = []
  const api = mockApi(calls)
  api.getRunStatus = async () => ({ data: { runner_status: 'completed', current_round: 72, total_rounds: 72 } })
  api.stopSimulation = async () => { calls.push('stop'); return { data: {} } }
  const d = deps(api)
  await runOne({ _tmpId: 'h2', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1', realSimId: 'sim_1', status: 'running' }, d)
  assert.ok(calls.includes('report'))
  assert.ok(!calls.includes('stop'), 'already terminal: no stop needed')
})

// 后端拒绝在 run 非终态时生成报告；持久化进程永远停在 running。
// 浏览器驱动器此前直接 generateReport -> 409 -> best-effort 吞掉 -> 标记 done，
// 结果是「完成但没有报告」的空任务，用户完全看不到原因。
test('held-open run: closes the env first, then reports (no silent report-less done)', async () => {
  const calls = []
  const api = mockApi(calls)
  let closed = false
  api.getRunStatus = async () => ({ data: {
    runner_status: closed ? 'completed' : 'running',
    current_round: 72, total_rounds: 72,
    twitter_completed: true, reddit_completed: true } })
  api.closeSimulationEnv = async () => { calls.push('close-env'); closed = true; return { data: { success: true } } }
  api.stopSimulation = async () => { calls.push('stop'); return { data: {} } }
  const d = deps(api)
  await runOne({ _tmpId: 'c1', file: {}, prompt: 'p', projectId: 'p', graphId: 'g', realSimId: 'sim_1', status: 'running' }, d)
  assert.ok(calls.includes('close-env'), 'must gracefully close the held-open env')
  assert.ok(calls.indexOf('close-env') < calls.indexOf('report'), 'report only after terminal')
  assert.equal(d._rec.statuses.at(-1), 'done')
})

test('close-env failure falls back to force stop before reporting', async () => {
  const calls = []
  const api = mockApi(calls)
  let closed = false
  api.getRunStatus = async () => ({ data: {
    runner_status: closed ? 'stopped' : 'running',
    current_round: 72, total_rounds: 72,
    twitter_completed: true, reddit_completed: true } })
  api.closeSimulationEnv = async () => { calls.push('close-env'); throw new Error('env not responding') }
  api.stopSimulation = async () => { calls.push('stop'); closed = true; return { data: {} } }
  await runOne({ _tmpId: 'c2', file: {}, prompt: 'p', projectId: 'p', graphId: 'g', realSimId: 'sim_1', status: 'running' }, deps(api))
  assert.ok(calls.indexOf('stop') < calls.indexOf('report'))
})

test('a rejected report fails the job instead of finishing report-less', async () => {
  const calls = []
  const api = mockApi(calls)
  api.getRunStatus = async () => ({ data: { runner_status: 'completed' } })
  api.generateReport = async () => { throw new Error('409 CONFLICT') }
  const patches = []
  const d = deps(api)
  d.store.patch = (_id, p) => patches.push(p)
  await runOne({ _tmpId: 'c3', file: {}, prompt: 'p', projectId: 'p', graphId: 'g', realSimId: 'sim_1', status: 'running' }, d)
  assert.equal(d._rec.statuses.at(-1), 'failed')
  assert.ok(patches.some(p => /409/.test(p.error || '')))
})
