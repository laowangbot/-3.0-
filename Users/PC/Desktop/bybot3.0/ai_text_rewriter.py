class AITextRewriter:
    """AI文本改写器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化AI文本改写器"""
        self.config = config or {}
        self.quota_manager = QuotaManager()
        self.model = None
        self.enabled = self.config.get('ai_rewrite_enabled', False)
        self.intensity = self.config.get('ai_rewrite_intensity', 'medium')
        
        # 初始化Gemini API
        api_key = self.config.get('gemini_api_key', 'AIzaSyDwZv1u_mWakdARed-yVTXjR3v1Ma9PbWE')
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # 尝试初始化新模型，如果失败则回退到旧模型
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-flash-live')  # 使用无速率限制的版本
                    logger.info("🤖 Gemini API 初始化成功 (使用 gemini-2.5-flash-live)")
                except Exception as e:
                    logger.warning(f"⚠️ gemini-2.5-flash-live 初始化失败: {e}, 尝试回退到 gemini-2.5-flash")
                    self.model = genai.GenerativeModel('gemini-2.5-flash')
                    logger.info("🤖 Gemini API 初始化成功 (使用 gemini-2.5-flash)")
            except Exception as e:
                logger.error(f"❌ Gemini API 初始化失败: {e}")
        else:
            logger.warning("⚠️ 未配置Gemini API密钥，AI改写功能将无法使用")

    async def rewrite_text(self, text: str) -> Tuple[str, bool]:
        """
        改写文本内容
        
        Args:
            text: 原始文本
            
        Returns:
            Tuple[str, bool]: (改写后的文本, 是否进行了改写)
        """
        if not self.enabled or not text.strip() or not self.model:
            return text, False
        
        # 检查额度
        if not self.quota_manager.has_quota():
            logger.warning("🚫 Gemini API额度已用尽，使用原文")
            return text, False
        
        try:
            # 构造提示词
            prompt = self._build_prompt(text)
            
            # 调用Gemini API
            response = await asyncio.wait_for(
                self._call_gemini_api(prompt),
                timeout=30.0
            )
            
            rewritten_text = response.text.strip() if response and response.text else text
            
            # 记录实际使用量（这里简化处理）
            input_tokens = len(text) // 4  # 粗略估算
            estimated_output_tokens = len(rewritten_text) // 4
            self.quota_manager.record_usage(input_tokens, estimated_output_tokens)
            
            # 如果文本没有实质性改变，则不标记为已改写
            if rewritten_text.strip() == text.strip():
                return text, False
            
            logger.debug(f"🔄 AI文本改写成功: '{text[:50]}...' -> '{rewritten_text[:50]}...'")
            return rewritten_text, True
            
        except asyncio.TimeoutError:
            logger.error("❌ AI文本改写超时")
            return text, False
        except Exception as e:
            logger.error(f"❌ AI文本改写失败: {e}")
            return text, False
    
    def _build_prompt(self, text: str) -> str:
        """构建提示词"""