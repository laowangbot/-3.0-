# ==================== 多机器人配置管理器 ====================
"""
多机器人配置管理器
支持多个机器人实例的独立配置和session管理
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class MultiBotConfigManager:
    """多机器人配置管理器"""
    
    def __init__(self, config_dir: str = "bot_configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.active_bots = {}
    
    def create_bot_config(self, bot_name: str, config_data: Dict[str, Any]) -> str:
        """为特定机器人创建配置文件"""
        config_file = self.config_dir / f"{bot_name}.json"
        
        # 确保session文件名唯一
        bot_token = config_data.get('bot_token', '')
        if bot_token and bot_token != 'your_bot_token':
            token_suffix = bot_token.split(':')[0][:8] if ':' in bot_token else bot_token[:8]
            config_data['session_name'] = f"bot_session_{token_suffix}"
        else:
            config_data['session_name'] = f"bot_session_{bot_name}"
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ 已为机器人 '{bot_name}' 创建配置文件: {config_file}")
        return str(config_file)
    
    def load_bot_config(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """加载特定机器人的配置"""
        config_file = self.config_dir / f"{bot_name}.json"
        
        if not config_file.exists():
            logger.error(f"❌ 机器人 '{bot_name}' 的配置文件不存在: {config_file}")
            return None
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"✅ 已加载机器人 '{bot_name}' 的配置")
            return config
        except Exception as e:
            logger.error(f"❌ 加载机器人 '{bot_name}' 配置失败: {e}")
            return None
    
    def list_bot_configs(self) -> list:
        """列出所有可用的机器人配置"""
        configs = []
        for config_file in self.config_dir.glob("*.json"):
            bot_name = config_file.stem
            configs.append(bot_name)
        return configs
    
    def delete_bot_config(self, bot_name: str) -> bool:
        """删除特定机器人的配置"""
        config_file = self.config_dir / f"{bot_name}.json"
        
        if not config_file.exists():
            logger.warning(f"⚠️ 机器人 '{bot_name}' 的配置文件不存在")
            return False
        
        try:
            config_file.unlink()
            logger.info(f"✅ 已删除机器人 '{bot_name}' 的配置")
            return True
        except Exception as e:
            logger.error(f"❌ 删除机器人 '{bot_name}' 配置失败: {e}")
            return False
    
    def get_session_file(self, bot_name: str) -> str:
        """获取特定机器人的session文件名"""
        config = self.load_bot_config(bot_name)
        if config:
            return config.get('session_name', f"bot_session_{bot_name}")
        return f"bot_session_{bot_name}"
    
    def validate_bot_config(self, config: Dict[str, Any]) -> bool:
        """验证机器人配置的完整性"""
        # 检查bot_token
        if not config.get('bot_token') or config.get('bot_token') == 'your_bot_token':
            logger.error(f"❌ 配置验证失败: bot_token 未设置或为占位符")
            return False
        
        # 检查api_id（必须是有效的整数）
        api_id = config.get('api_id')
        if not api_id or api_id == 0 or api_id == 'your_api_id':
            logger.error(f"❌ 配置验证失败: api_id 未设置或为占位符 (当前值: {api_id})")
            return False
        
        # 检查api_hash
        if not config.get('api_hash') or config.get('api_hash') == 'your_api_hash':
            logger.error(f"❌ 配置验证失败: api_hash 未设置或为占位符")
            return False
        
        return True
    
    def detect_deployment_environment(self) -> str:
        """检测部署环境"""
        # 检查是否在Render环境
        if os.getenv('RENDER') or os.getenv('DEPLOYMENT_MODE') == 'render':
            return 'render'
        # 检查是否在Heroku环境
        elif os.getenv('DYNO'):
            return 'heroku'
        # 检查是否在Docker环境
        elif os.path.exists('/.dockerenv'):
            return 'docker'
        # 默认为本地环境
        else:
            return 'local'
    
    def load_bot_config_from_environment(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """从环境变量或.env文件加载机器人配置"""
        env_type = self.detect_deployment_environment()
        
        if env_type == 'render':
            # Render环境：从环境变量加载
            return self._load_from_render_env(bot_name)
        else:
            # 本地环境：从.env文件加载
            return self._load_from_env_file(bot_name)
    
    def _load_from_render_env(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """从Render环境变量加载配置"""
        try:
            logger.info(f"🔍 开始从Render环境变量加载机器人 '{bot_name}' 的配置")
            
            # 获取BOT_INSTANCE环境变量来确定实际的机器人名称
            bot_instance = os.getenv('BOT_INSTANCE')
            if bot_instance:
                # 如果BOT_INSTANCE设置了，使用它作为机器人名称
                actual_bot_name = bot_instance.lower()
                logger.info(f"🔍 检测到BOT_INSTANCE: {bot_instance}, 使用机器人名称: {actual_bot_name}")
            else:
                actual_bot_name = bot_name
            
            # 检查是否有特定机器人的环境变量前缀
            bot_prefix = f"{actual_bot_name.upper()}_"
            
            # 获取API ID和API Hash
            api_id_str = os.getenv(f"{bot_prefix}API_ID") or os.getenv('API_ID')
            api_hash_str = os.getenv(f"{bot_prefix}API_HASH") or os.getenv('API_HASH')
            
            # 获取Bot Token
            bot_token = os.getenv(f"{bot_prefix}BOT_TOKEN") or os.getenv('BOT_TOKEN')
            
            logger.info(f"🔍 环境变量检查:")
            logger.info(f"   BOT_INSTANCE: {bot_instance}")
            logger.info(f"   实际机器人名称: {actual_bot_name}")
            logger.info(f"   环境变量前缀: {bot_prefix}")
            logger.info(f"   {bot_prefix}API_ID: {api_id_str}")
            logger.info(f"   {bot_prefix}API_HASH: {api_hash_str}")
            logger.info(f"   {bot_prefix}BOT_TOKEN: {bot_token[:10] + '...' if bot_token else 'None'}")
            
            # 额外的调试信息
            logger.info(f"🔍 额外调试信息:")
            logger.info(f"   os.getenv('WANG_API_ID'): {os.getenv('WANG_API_ID')}")
            logger.info(f"   os.getenv('WANG_API_HASH'): {os.getenv('WANG_API_HASH')}")
            logger.info(f"   os.getenv('WANG_BOT_TOKEN'): {os.getenv('WANG_BOT_TOKEN')}")
            logger.info(f"   os.getenv('API_ID'): {os.getenv('API_ID')}")
            logger.info(f"   os.getenv('API_HASH'): {os.getenv('API_HASH')}")
            logger.info(f"   os.getenv('BOT_TOKEN'): {os.getenv('BOT_TOKEN')}")
            
            # 智能检测和修复：如果API_ID看起来像API_HASH（包含字母），则交换
            if api_id_str and not api_id_str.isdigit() and len(api_id_str) > 10:
                logger.warning(f"⚠️ 检测到API_ID和API_HASH可能被交换，尝试自动修复")
                # 交换值
                temp = api_id_str
                api_id_str = api_hash_str
                api_hash_str = temp
                logger.info(f"🔄 已交换API_ID和API_HASH值")
            
            try:
                api_id = int(api_id_str) if api_id_str else 0
            except (ValueError, TypeError):
                logger.error(f"❌ API_ID格式错误: {api_id_str}")
                api_id = 0
            
            config = {
                "bot_name": actual_bot_name,
                "bot_token": bot_token,
                "api_id": api_id,
                "api_hash": api_hash_str,
                "firebase_project_id": os.getenv(f"{bot_prefix}FIREBASE_PROJECT_ID") or os.getenv('FIREBASE_PROJECT_ID'),
                "use_local_storage": os.getenv(f"{bot_prefix}USE_LOCAL_STORAGE", "false").lower() == "true",
                "is_render": True,
                "port": int(os.getenv('PORT', 8080)),
                "session_name": f"render_bot_session_{actual_bot_name}",
                "description": f"机器人 {actual_bot_name} 的Render配置"
            }
            
            logger.info(f"🔍 配置验证结果:")
            logger.info(f"   bot_token: {'✅' if config['bot_token'] and config['bot_token'] != 'your_bot_token' else '❌'}")
            logger.info(f"   api_id: {'✅' if config['api_id'] > 0 else '❌'}")
            logger.info(f"   api_hash: {'✅' if config['api_hash'] and config['api_hash'] != 'your_api_hash' else '❌'}")
            
            if self.validate_bot_config(config):
                logger.info(f"✅ 已从Render环境变量加载机器人 '{actual_bot_name}' 的配置")
                return config
            else:
                logger.error(f"❌ Render环境变量配置不完整")
                return None
                
        except Exception as e:
            logger.error(f"❌ 从Render环境变量加载配置失败: {e}")
            return None
    
    def _load_from_env_file(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """从.env文件加载配置"""
        try:
            from dotenv import load_dotenv
            
            # 尝试加载特定机器人的.env文件
            env_file = f".env.{bot_name}"
            if os.path.exists(env_file):
                # 尝试不同的编码方式
                try:
                    load_dotenv(env_file, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        load_dotenv(env_file, encoding='utf-8-sig')
                    except UnicodeDecodeError:
                        load_dotenv(env_file, encoding='utf-16')
                logger.info(f"✅ 已加载环境文件: {env_file}")
            else:
                # 回退到默认.env文件
                if os.path.exists('.env'):
                    # 尝试不同的编码方式
                    try:
                        load_dotenv('.env', encoding='utf-8')
                    except UnicodeDecodeError:
                        try:
                            load_dotenv('.env', encoding='utf-8-sig')
                        except UnicodeDecodeError:
                            load_dotenv('.env', encoding='utf-16')
                    logger.debug("✅ 已加载默认环境文件: .env")
                else:
                    logger.warning("⚠️ 未找到环境文件")
                    return None
            
            # 获取API ID和API Hash
            api_id_str = os.getenv('API_ID')
            api_hash_str = os.getenv('API_HASH')
            
            # 智能检测和修复：如果API_ID看起来像API_HASH（包含字母），则交换
            if api_id_str and not api_id_str.isdigit() and len(api_id_str) > 10:
                logger.warning(f"⚠️ 检测到API_ID和API_HASH可能被交换，尝试自动修复")
                # 交换值
                temp = api_id_str
                api_id_str = api_hash_str
                api_hash_str = temp
                logger.info(f"🔄 已交换API_ID和API_HASH值")
            
            try:
                api_id = int(api_id_str) if api_id_str else 0
            except (ValueError, TypeError):
                logger.error(f"❌ API_ID格式错误: {api_id_str}")
                api_id = 0
            
            config = {
                "bot_name": bot_name,
                "bot_token": os.getenv('BOT_TOKEN'),
                "api_id": api_id,
                "api_hash": api_hash_str,
                "firebase_project_id": os.getenv('FIREBASE_PROJECT_ID'),
                "use_local_storage": os.getenv('USE_LOCAL_STORAGE', 'false').lower() == 'true',
                "is_render": False,
                "port": int(os.getenv('PORT', 8080)),
                "session_name": f"bot_session_{bot_name}",
                "description": f"机器人 {bot_name} 的本地配置"
            }
            
            if self.validate_bot_config(config):
                logger.debug(f"✅ 已从环境文件加载机器人 '{bot_name}' 的配置")
                return config
            else:
                logger.error(f"❌ 环境文件配置不完整")
                return None
                
        except Exception as e:
            logger.error(f"❌ 从环境文件加载配置失败: {e}")
            return None

# 创建全局实例
multi_bot_manager = MultiBotConfigManager()

def create_bot_config_template(bot_name: str) -> Dict[str, Any]:
    """创建机器人配置模板"""
    return {
        "bot_name": bot_name,
        "bot_token": "your_bot_token",
        "api_id": "your_api_id", 
        "api_hash": "your_api_hash",
        "firebase_project_id": "your_project_id",
        "use_local_storage": True,
        "is_render": False,
        "port": 8080,
        "session_name": f"bot_session_{bot_name}",
        "description": f"机器人 {bot_name} 的配置",
        "env_file": f".env.{bot_name}",  # 本地环境文件
        "render_service": f"{bot_name}-service"  # Render服务名称
    }

def create_env_file_template(bot_name: str) -> str:
    """创建.env文件模板"""
    env_content = f"""# ==================== 机器人 {bot_name} 环境配置 ====================
# 请填入实际的配置值

# Telegram Bot配置
BOT_TOKEN=your_bot_token
API_ID=your_api_id
API_HASH=your_api_hash

# Firebase配置
FIREBASE_PROJECT_ID=your_project_id

# 存储模式 (true=本地存储, false=Firebase存储)
USE_LOCAL_STORAGE=true

# 端口配置
PORT=8080

# 部署环境 (true=Render环境, false=本地环境)
IS_RENDER=false
"""
    
    env_file = f".env.{bot_name}"
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    return env_file

def setup_multi_bot_environment():
    """设置多机器人环境"""
    logger.info("🔧 设置多机器人环境...")
    
    # 创建配置目录
    config_dir = Path("bot_configs")
    config_dir.mkdir(exist_ok=True)
    
    # 创建示例配置
    example_config = create_bot_config_template("example_bot")
    example_file = config_dir / "example_bot.json"
    
    if not example_file.exists():
        with open(example_file, 'w', encoding='utf-8') as f:
            json.dump(example_config, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 已创建示例配置文件: {example_file}")
    
    # 创建示例.env文件
    example_env_file = create_env_file_template("example_bot")
    logger.info(f"✅ 已创建示例环境文件: {example_env_file}")
    
    logger.info("✅ 多机器人环境设置完成")
    logger.info(f"📁 配置文件目录: {config_dir.absolute()}")
    logger.info("💡 使用方法:")
    logger.info("   1. 复制 .env.example_bot 为 .env.<你的机器人名称>")
    logger.info("   2. 编辑.env文件，填入实际的配置值")
    logger.info("   3. 使用 python lsjmain.py --bot <机器人名称> 启动")
    logger.info("   4. 或者使用 python lsjmain.py --create-bot <机器人名称> 创建新配置")

if __name__ == "__main__":
    setup_multi_bot_environment()
