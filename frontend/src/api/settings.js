import service from './index'

/**
 * 读取部署级设置（思考深度等）
 */
export const getSettings = () => {
  return service.get('/api/settings')
}

/**
 * 更新设置
 * @param {{think_level: ('economy'|'deep')}} data
 */
export const updateSettings = (data) => {
  return service.post('/api/settings', data)
}
