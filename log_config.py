# ==================== 日志配置 ====================
"""
统一的日志配置管理
支持不同级别的日志输出，减少冗余信息
"""

import logging
import sys
import time
from typing import Optional

class LogConfig:
    """日志配置类"""
    
    # 日志级别配置
    LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    @staticmethod
    def setup_logging(level: str = 'INFO', 
                     format_str: Optional[str] = None,
                     enable_file_logging: bool = False,
                     log_file: str = 'bot.log') -> logging.Logger:
        """
        设置统一的日志配置
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            format_str: 自定义日志格式
            enable_file_logging: 是否启用文件日志
            log_file: 日志文件名
        """
        # 默认格式 - 更简洁的格式
        if format_str is None:
            format_str = '%(levelname)s:%(name)s:%(message)s'
        
        # 获取日志级别
        log_level = LogConfig.LEVELS.get(level.upper(), logging.INFO)
        
        # 清除现有的处理器
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 创建格式化器
        formatter = logging.Formatter(format_str)
        
        # 控制台处理器 - 设置UTF-8编码
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        
        # 设置输出编码为UTF-8
        if hasattr(console_handler.stream, 'reconfigure'):
            console_handler.stream.reconfigure(encoding='utf-8')
        
        # 添加处理器
        root_logger.addHandler(console_handler)
        root_logger.setLevel(log_level)
        
        # 文件处理器（可选）
        if enable_file_logging:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        
        # 设置特定模块的日志级别
        LogConfig._configure_module_levels(log_level)
        
        return root_logger
    
    @staticmethod
    def _configure_module_levels(base_level: int):
        """配置特定模块的日志级别"""
        # 减少第三方库的日志输出
        logging.getLogger('pyrogram').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        logging.getLogger('requests').setLevel(logging.ERROR)
        logging.getLogger('aiohttp').setLevel(logging.ERROR)
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        logging.getLogger('telethon').setLevel(logging.ERROR)
        
        # 设置主要模块的日志级别
        if base_level <= logging.DEBUG:
            # 调试模式下，显示所有模块的详细信息
            pass
        else:
            # 生产模式下，减少详细调试信息
            logging.getLogger('message_engine').setLevel(logging.WARNING)
            logging.getLogger('monitoring_engine').setLevel(logging.INFO)  # 保持INFO级别以显示监听日志
            logging.getLogger('cloning_engine').setLevel(logging.INFO)
            logging.getLogger('main').setLevel(logging.INFO)
            
            # 特别优化监听引擎的日志输出
            LogConfig._optimize_monitoring_logs()
    
    @staticmethod
    def _optimize_monitoring_logs():
        """优化监听引擎的日志输出，减少冗余信息"""
        # 创建自定义过滤器来减少重复日志
        class MonitoringLogFilter(logging.Filter):
            def __init__(self):
                self.last_log_time = {}
                self.log_interval = 30  # 相同日志间隔30秒
                
            def filter(self, record):
                # 过滤掉过于频繁的轮询日志
                if '轮询检查消息' in record.getMessage():
                    return False
                if '收到任何消息' in record.getMessage():
                    return False
                if '检测到媒体组消息' in record.getMessage():
                    return False
                if '消息已处理过' in record.getMessage():
                    return False
                if '媒体组已处理过' in record.getMessage():
                    return False
                
                # 限制重复的检查日志
                if '检查监听任务' in record.getMessage():
                    current_time = time.time()
                    if 'check_task' in self.last_log_time:
                        if current_time - self.last_log_time['check_task'] < 60:  # 60秒内不重复
                            return False
                    self.last_log_time['check_task'] = current_time
                
                return True
        
        # 应用过滤器到监听引擎
        monitoring_logger = logging.getLogger('monitoring_engine')
        monitoring_logger.addFilter(MonitoringLogFilter())
        
        # 保持INFO级别以显示监听日志
        monitoring_logger.setLevel(logging.INFO)
    
    @staticmethod
    def get_optimized_logger(name: str, level: str = 'INFO') -> logging.Logger:
        """
        获取优化后的日志记录器
        
        Args:
            name: 模块名称
            level: 日志级别
        """
        logger = logging.getLogger(name)
        
        # 设置日志级别
        log_level = LogConfig.LEVELS.get(level.upper(), logging.INFO)
        logger.setLevel(log_level)
        
        return logger

# 便捷函数
def setup_bot_logging(level: str = 'INFO', enable_file: bool = False) -> logging.Logger:
    """设置机器人日志配置"""
    return LogConfig.setup_logging(
        level=level,
        enable_file_logging=enable_file,
        log_file='bot.log'
    )

def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    return LogConfig.get_optimized_logger(name)

