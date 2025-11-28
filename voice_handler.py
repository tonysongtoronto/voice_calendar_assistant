import whisper
from gtts import gTTS
import io
import base64
import tempfile
import logging
import os
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

class VoiceHandler:
    def __init__(self):
        logger.info("🎤 正在加载 Whisper 模型...")
        # 使用 base 模型，平衡速度和准确性
        # 可选模型: tiny (最快), base (推荐), small, medium, large (最准确但最慢)
        self.whisper_model = whisper.load_model("base")
        logger.info("✅ Whisper 模型加载完成")
    
    async def speech_to_text(self, audio_bytes: bytes) -> str:
        """
        语音转文字
        
        Args:
            audio_bytes: 音频文件的字节数据
            
        Returns:
            str: 识别出的文字
        """
        temp_path = None
        try:
            # 保存临时音频文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name
            
            logger.info(f"📝 音频文件大小: {len(audio_bytes)} 字节")
            logger.info(f"🎧 开始语音识别...")
            
            # Whisper 是阻塞操作，在线程池中运行以避免阻塞事件循环
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.whisper_model.transcribe(
                    temp_path, 
                    language="zh",
                    fp16=False  # 如果在 CPU 上运行，禁用 FP16
                )
            )
            
            text = result["text"].strip()
            
            if text:
                logger.info(f"✅ 语音识别成功: {text}")
            else:
                logger.warning("⚠️ 语音识别结果为空")
            
            return text
            
        except Exception as e:
            logger.error(f"❌ 语音识别失败: {e}", exc_info=True)
            return ""
        
        finally:
            # 清理临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    logger.debug(f"🗑️ 已删除临时文件: {temp_path}")
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")
    
    async def text_to_speech(self, text: str) -> str:
        """
        文字转语音，返回 base64 编码的音频
        
        Args:
            text: 要转换的文字
            
        Returns:
            str: base64 编码的 MP3 音频数据
        """
        try:
            if not text:
                logger.warning("⚠️ TTS 输入文本为空")
                return ""
            
            logger.info(f"🎤 开始文字转语音: {text[:50]}{'...' if len(text) > 50 else ''}")
            
            # gTTS 涉及网络请求，在线程池中运行
            loop = asyncio.get_event_loop()
            
            def generate_speech():
                tts = gTTS(text=text, lang='zh-cn', slow=False)
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                return fp.read()
            
            audio_data = await loop.run_in_executor(None, generate_speech)
            
            # 转为 base64
            audio_base64 = base64.b64encode(audio_data).decode()
            
            logger.info(f"✅ 语音合成成功，音频大小: {len(audio_data)} 字节")
            return audio_base64
            
        except Exception as e:
            logger.error(f"❌ 语音合成失败: {e}", exc_info=True)
            return ""
    
    async def test_voice_pipeline(self):
        """测试完整的语音处理流程"""
        try:
            logger.info("=" * 60)
            logger.info("🧪 开始测试语音处理流程")
            logger.info("=" * 60)
            
            # 1. 测试 TTS
            test_text = "你好，这是一个语音测试。"
            logger.info(f"1️⃣ 测试文字转语音: {test_text}")
            audio_base64 = await self.text_to_speech(test_text)
            
            if audio_base64:
                logger.info("✅ TTS 测试通过")
                
                # 保存测试音频
                audio_data = base64.b64decode(audio_base64)
                test_file = Path("test_tts_output.mp3")
                with open(test_file, "wb") as f:
                    f.write(audio_data)
                logger.info(f"📁 测试音频已保存: {test_file}")
            else:
                logger.error("❌ TTS 测试失败")
                return False
            
            logger.info("=" * 60)
            logger.info("✅ 所有测试通过！")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"❌ 测试失败: {e}", exc_info=True)
            return False

# 测试代码
async def test_voice_handler():
    """测试 VoiceHandler"""
    handler = VoiceHandler()
    await handler.test_voice_pipeline()

if __name__ == "__main__":
    # 运行测试
    import asyncio
    asyncio.run(test_voice_handler())