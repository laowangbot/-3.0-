#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web服务器模块
为Render部署提供HTTP心跳端点
"""

import asyncio
import logging
from datetime import datetime
from aiohttp import web, ClientSession
import json
from config import get_config

logger = logging.getLogger(__name__)

class WebServer:
    """Web服务器类，提供心跳和状态端点"""
    
    def __init__(self, bot_instance=None):
        """初始化Web服务器"""
        self.config = get_config()
        self.bot_instance = bot_instance
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/', self.health_check)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.bot_status)
        self.app.router.add_get('/ping', self.ping)
        
    async def health_check(self, request):
        """健康检查端点"""
        return web.json_response({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'service': 'telegram-bot',
            'version': '3.0'
        })
        
    async def ping(self, request):
        """简单的ping端点"""
        return web.Response(text='pong')
        
    async def bot_status(self, request):
        """机器人状态端点"""
        try:
            status_data = {
                'timestamp': datetime.now().isoformat(),
                'bot_running': False,
                'client_connected': False,
                'active_tasks': 0
            }
            
            if self.bot_instance:
                status_data['bot_running'] = True
                
                if hasattr(self.bot_instance, 'client') and self.bot_instance.client:
                    status_data['client_connected'] = self.bot_instance.client.is_connected
                    
                if hasattr(self.bot_instance, 'cloning_engine') and self.bot_instance.cloning_engine:
                    status_data['active_tasks'] = len(self.bot_instance.cloning_engine.active_tasks)
                    
            return web.json_response(status_data)
            
        except Exception as e:
            logger.error(f"获取机器人状态失败: {e}")
            return web.json_response({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }, status=500)
            
    async def start_server(self, host='0.0.0.0', port=None):
        """启动Web服务器"""
        if port is None:
            port = self.config.get('port', 8080)
            
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, host, port)
            await site.start()
            
            logger.info(f"🌐 Web服务器已启动: http://{host}:{port}")
            logger.info(f"🔍 健康检查端点: http://{host}:{port}/health")
            logger.info(f"📊 状态端点: http://{host}:{port}/status")
            
            return runner
            
        except Exception as e:
            logger.error(f"启动Web服务器失败: {e}")
            raise
            
    async def keep_alive(self):
        """保持服务活跃的心跳任务"""
        render_url = self.config.get('render_external_url')
        
        if not render_url or render_url == 'your_render_url':
            logger.info("未配置Render URL，跳过自我心跳")
            return
            
        logger.info(f"启动自我心跳任务: {render_url}")
        
        async with ClientSession() as session:
            while True:
                try:
                    # 每25分钟ping一次自己，防止Render休眠
                    await asyncio.sleep(25 * 60)  # 25分钟
                    
                    async with session.get(f"{render_url}/ping", timeout=30) as response:
                        if response.status == 200:
                            logger.debug("自我心跳成功")
                        else:
                            logger.warning(f"自我心跳响应异常: {response.status}")
                            
                except asyncio.CancelledError:
                    logger.info("心跳任务被取消")
                    break
                except Exception as e:
                    logger.error(f"自我心跳失败: {e}")
                    # 继续循环，不要因为单次失败而停止
                    
async def create_web_server(bot_instance=None):
    """创建Web服务器实例"""
    return WebServer(bot_instance)