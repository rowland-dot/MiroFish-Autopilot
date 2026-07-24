"""
MiroFish Backend - Flask应用工厂
"""

import os
import warnings

# 抑制 multiprocessing resource_tracker 的警告（来自第三方库如 transformers）
# 需要在所有其他导入之前设置
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 设置JSON编码：确保中文直接显示（而不是 \uXXXX 格式）
    # Flask >= 2.3 使用 app.json.ensure_ascii，旧版本使用 JSON_AS_ASCII 配置
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # 设置日志
    logger = setup_logger('mirofish')
    
    # 只在 reloader 子进程中打印启动信息（避免 debug 模式下打印两次）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend 启动中...")
        logger.info("=" * 50)
    
    # 启用CORS（暴露 Content-Disposition 供前端读取下载文件名）
    CORS(app, resources={r"/api/*": {"origins": "*"}}, expose_headers=['Content-Disposition'])

    # 访问口令门（AUTH_ENABLED=true 时生效，保护页面与所有 /api/* 接口）
    from .auth import init_auth
    init_auth(app)
    
    # 注册模拟进程清理函数（确保服务器关闭时终止所有模拟进程）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("已注册模拟进程清理函数")
    
    # 请求日志中间件
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"请求: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"请求体: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"响应: {response.status_code}")
        return response
    
    # 注册蓝图
    from .api import graph_bp, simulation_bp, report_bp
    from .api.settings import settings_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')

    # 备份 / 恢复接口（受访问口令门保护）
    from .api.backup import backup_bp
    app.register_blueprint(backup_bp, url_prefix='/api')

    # 系统状态（是否有任务在跑）——部署安全闸门用
    from .api.status import status_bp
    app.register_blueprint(status_bp, url_prefix='/api')

    # 多 Zep 账号密钥管理（ZEP_API_KEY(, ZEP_API_KEY_2, …)）——额度耗尽自动切换
    from .utils import zep_client
    zep_client.init_manager(os.environ)

    # 每日自动备份到私有 HF Dataset（仅当配置了 BACKUP_HF_REPO + HF_TOKEN 时启动）
    from .services.backup_scheduler import start_backup_scheduler
    start_backup_scheduler(Config.UPLOAD_FOLDER)

    # 单容器部署：若存在已构建的前端（frontend/dist），由 Flask 同端口伺服
    from .static_site import init_static_site
    default_dist = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'dist')
    init_static_site(app, os.environ.get('STATIC_DIST', default_dist))
    
    # 健康检查
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info("MiroFish Backend 启动完成")
    
    return app

