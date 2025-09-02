# Render部署故障排除指南

## 🔍 SIGTERM信号分析

从您的日志可以看到：
```
INFO:__main__:收到 SIGTERM，开始关闭机器人...
INFO:__main__:收到停止信号，开始关闭...
```

SIGTERM信号是Render平台发送的停止信号，常见原因如下：

## 🚨 常见停止原因

### 1. 内存使用超限
**Free计划限制**: 512MB RAM
**症状**: 内存使用超过限制
**解决方案**: 
- 优化代码，减少内存占用
- 升级到Starter计划 (512MB RAM)
- 添加内存监控

### 2. 健康检查失败
**默认健康检查**: `/health` 端点
**症状**: 健康检查超时或返回错误
**解决方案**:
- 确保 `/health` 端点正常响应
- 检查健康检查超时设置
- 添加更详细的健康检查逻辑

### 3. 启动超时
**Free计划限制**: 90秒启动时间
**症状**: 应用启动时间过长
**解决方案**:
- 优化启动流程
- 减少初始化时间
- 使用异步初始化

### 4. 无活动超时
**Free计划限制**: 15分钟无活动后休眠
**症状**: 应用长时间无请求后自动停止
**解决方案**:
- 配置自我心跳
- 使用外部监控服务
- 升级到付费计划

### 5. 错误导致崩溃
**症状**: 未捕获的异常导致应用崩溃
**解决方案**:
- 添加全局异常处理
- 改进错误日志
- 添加自动重启机制

## 🔧 诊断步骤

### 1. 检查Render日志
在Render控制台查看详细日志：
- 内存使用情况
- 错误信息
- 启动时间

### 2. 添加监控
```python
import psutil
import logging

def log_system_info():
    memory = psutil.virtual_memory()
    logger.info(f"内存使用: {memory.percent}% ({memory.used/1024/1024:.1f}MB/{memory.total/1024/1024:.1f}MB)")
```

### 3. 改进健康检查
```python
@app.route('/health')
async def health_check():
    try:
        # 检查数据库连接
        await data_manager.health_check()
        
        # 检查内存使用
        memory = psutil.virtual_memory()
        if memory.percent > 80:
            return {"status": "warning", "memory": memory.percent}, 200
        
        return {"status": "healthy", "memory": memory.percent}, 200
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500
```

## 🛠️ 优化建议

### 1. 内存优化
- 减少全局变量
- 及时释放大对象
- 使用生成器而非列表
- 限制并发任务数量

### 2. 启动优化
- 延迟加载非关键组件
- 使用异步初始化
- 减少启动时的网络请求

### 3. 错误处理
- 添加全局异常处理器
- 改进日志记录
- 实现优雅关闭

### 4. 监控改进
- 添加性能指标
- 实现自我监控
- 配置告警机制

## 📊 建议的改进

### 1. 添加系统监控
```python
import psutil
import asyncio

class SystemMonitor:
    def __init__(self):
        self.monitoring = False
    
    async def start_monitoring(self):
        self.monitoring = True
        while self.monitoring:
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                logger.warning(f"内存使用过高: {memory.percent}%")
            
            await asyncio.sleep(30)  # 每30秒检查一次
```

### 2. 改进健康检查
```python
@app.route('/health')
async def health_check():
    try:
        # 基本健康检查
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime": time.time() - start_time,
            "memory_usage": psutil.virtual_memory().percent,
            "bot_status": "running" if bot.initialized else "initializing"
        }
        
        # 检查关键组件
        if not bot.initialized:
            health_data["status"] = "initializing"
        
        return health_data, 200
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500
```

### 3. 添加自我心跳
```python
async def self_heartbeat():
    """自我心跳，防止Render休眠"""
    while True:
        try:
            # 发送心跳请求
            if config.get('render_external_url'):
                async with aiohttp.ClientSession() as session:
                    await session.get(f"{config['render_external_url']}/health")
            await asyncio.sleep(300)  # 每5分钟一次
        except Exception as e:
            logger.warning(f"心跳失败: {e}")
            await asyncio.sleep(60)  # 失败后1分钟重试
```

## 🎯 立即行动建议

1. **检查Render日志** - 查看具体的停止原因
2. **添加内存监控** - 实时监控内存使用
3. **改进健康检查** - 提供更详细的健康状态
4. **配置自我心跳** - 防止无活动休眠
5. **优化启动流程** - 减少启动时间

---

**下一步**: 请检查Render控制台的详细日志，确定具体的停止原因。
