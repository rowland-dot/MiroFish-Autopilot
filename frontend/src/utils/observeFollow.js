// Which live page corresponds to a pipeline entry's current stage.
//
// When the user is watching a driver-run job (?observe=1), the page must
// FOLLOW the pipeline as it advances — the step pages no longer advance
// themselves (that used to double-drive the pipeline: duplicate prepares,
// restarted runs). Navigation is a pure view change; it drives nothing.

export function targetRouteForEntry(entry) {
  if (!entry) return null
  const q = { observe: '1' }
  if (entry.reportId) {
    return { name: 'Report', params: { reportId: entry.reportId } }   // report has its own view
  }
  if (entry.status === 'running' && entry.realSimId) {
    return { name: 'SimulationRun', params: { simulationId: entry.realSimId }, query: q }
  }
  if (entry.realSimId) {
    return { name: 'Simulation', params: { simulationId: entry.realSimId }, query: q }
  }
  if (entry.projectId) {
    return { name: 'Process', params: { projectId: entry.projectId }, query: q }
  }
  return null   // ontology stage: nothing to show yet
}

// The entry the user is currently watching, matched off the route params.
export function observedEntry(entries, routeName, params) {
  const list = Array.isArray(entries) ? entries : []
  const p = params || {}
  if (p.simulationId) {
    return list.find(e => e.realSimId === p.simulationId) || null
  }
  if (p.projectId && p.projectId !== 'new') {
    return list.find(e => e.projectId === p.projectId) || null
  }
  return null
}

// True when we should navigate: target exists and differs from where we are.
export function shouldFollow(target, routeName, params) {
  if (!target) return false
  const p = params || {}
  if (target.name !== routeName) return true
  if (target.params.simulationId && target.params.simulationId !== p.simulationId) return true
  if (target.params.projectId && target.params.projectId !== p.projectId) return true
  if (target.params.reportId && target.params.reportId !== p.reportId) return true
  return false
}
