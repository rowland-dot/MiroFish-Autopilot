import service from './index'

/** 读取服务器端流水线条目（队列 + 卡片状态） */
export const getPipeline = () => service.get('/api/pipeline')

/** 新增/更新一条条目（按 tmpId 覆盖） */
export const putPipelineEntry = (entry) => service.post('/api/pipeline', entry)

/** 删除一条条目（幂等） */
export const deletePipelineEntry = (tmpId) => service.delete(`/api/pipeline/${tmpId}`)
