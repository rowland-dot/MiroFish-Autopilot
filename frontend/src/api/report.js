import service, { requestWithRetry } from './index'
import { filenameFromDisposition } from '../utils/downloadName'

/**
 * 开始报告生成
 * @param {Object} data - { simulation_id, force_regenerate? }
 */
export const generateReport = (data) => {
  return service.post('/api/report/generate', data)
}

/**
 * 获取报告生成状态
 * @param {string} reportId
 */
export const getReportStatus = (reportId) => {
  return service.get(`/api/report/generate/status`, { params: { report_id: reportId } })
}

/**
 * 获取 Agent 日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getAgentLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * 获取控制台日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getConsoleLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/**
 * 获取报告详情
 * @param {string} reportId
 */
export const getReport = (reportId) => {
  return service.get(`/api/report/${reportId}`)
}

/**
 * 与 Report Agent 对话
 * @param {Object} data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data) => {
  return service.post('/api/report/chat', data)
}

/**
 * 下载报告。用 fetch 以便读取服务端 Content-Disposition 中的真实文件名
 * （report_<原始文件名>.<格式>）。
 * @param {string} reportId
 * @param {('md'|'docx')} format
 * @returns {Promise<{blob: Blob, filename: string}>}
 */
export const downloadReport = async (reportId, format = 'md') => {
  const base = service.defaults.baseURL || ''
  const res = await fetch(`${base}/api/report/${reportId}/download?format=${format}`)
  if (!res.ok) throw new Error(`download failed: ${res.status}`)
  const blob = await res.blob()
  const filename = filenameFromDisposition(
    res.headers.get('content-disposition'),
    `${reportId}.${format}`
  )
  return { blob, filename }
}
