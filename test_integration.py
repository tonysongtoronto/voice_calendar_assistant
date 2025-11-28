"""
集成测试脚本 - 测试所有模块
"""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_voice_handler():
    """测试语音处理模块"""
    logger.info("=" * 80)
    logger.info("🧪 测试 1: 语音处理模块 (VoiceHandler)")
    logger.info("=" * 80)
    
    try:
        from voice_handler import VoiceHandler
        
        handler = VoiceHandler()
        
        # 测试 TTS
        test_text = "你好，这是一个测试。"
        logger.info(f"测试文字转语音: {test_text}")
        
        audio_base64 = await handler.text_to_speech(test_text)
        
        if audio_base64:
            logger.info(f"✅ TTS 测试通过，音频长度: {len(audio_base64)} 字符")
            
            # 保存测试音频
            import base64
            audio_data = base64.b64decode(audio_base64)
            with open("test_voice_handler.mp3", "wb") as f:
                f.write(audio_data)
            logger.info("📁 测试音频已保存: test_voice_handler.mp3")
            return True
        else:
            logger.error("❌ TTS 测试失败")
            return False
            
    except Exception as e:
        logger.error(f"❌ VoiceHandler 测试失败: {e}", exc_info=True)
        return False

async def test_calendar_bot():
    """测试日历机器人"""
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("🧪 测试 2: 日历机器人 (CalendarBot)")
    logger.info("=" * 80)
    
    try:
        from calendar_bot import CalendarBot
        from datetime import datetime, timedelta
        
        bot = CalendarBot()
        await bot.initialize()
        
        # 测试创建事件
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        
        logger.info(f"测试创建事件: 测试会议 @ {start_time}")
        
        result = await bot.create_event("测试会议", start_time, end_time)
        
        await bot.close()
        
        if result['success']:
            logger.info(f"✅ CalendarBot 测试通过")
            logger.info(f"   事件: {result['title']}")
            logger.info(f"   时间: {result['date_str']} {result['time_str']}")
            return True
        else:
            logger.error(f"❌ CalendarBot 测试失败: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ CalendarBot 测试失败: {e}", exc_info=True)
        return False

async def test_dependencies():
    """测试依赖项"""
    logger.info("=" * 80)
    logger.info("🔍 检查依赖项")
    logger.info("=" * 80)
    
    dependencies = {
        "fastapi": "FastAPI 框架",
        "uvicorn": "ASGI 服务器",
        "whisper": "Whisper 语音识别",
        "gtts": "Google TTS",
        "playwright": "浏览器自动化",
    }
    
    all_ok = True
    
    for module, description in dependencies.items():
        try:
            __import__(module)
            logger.info(f"✅ {description} ({module})")
        except ImportError:
            logger.error(f"❌ {description} ({module}) - 未安装")
            all_ok = False
    
    logger.info("")
    return all_ok

async def main():
    """运行所有测试"""
    logger.info("\n")
    logger.info("🚀 开始集成测试")
    logger.info("=" * 80)
    
    # 1. 检查依赖
    deps_ok = await test_dependencies()
    if not deps_ok:
        logger.error("\n❌ 依赖项检查失败，请安装缺失的包")
        logger.info("\n安装命令:")
        logger.info("pip install fastapi uvicorn openai-whisper gtts playwright")
        logger.info("playwright install chromium")
        return
    
    # 2. 测试语音处理
    voice_ok = await test_voice_handler()
    
    # 3. 测试日历机器人
    calendar_ok = await test_calendar_bot()
    
    # 总结
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("📊 测试结果总结")
    logger.info("=" * 80)
    logger.info(f"依赖项检查: {'✅ 通过' if deps_ok else '❌ 失败'}")
    logger.info(f"语音处理:   {'✅ 通过' if voice_ok else '❌ 失败'}")
    logger.info(f"日历机器人: {'✅ 通过' if calendar_ok else '❌ 失败'}")
    logger.info("=" * 80)
    
    if deps_ok and voice_ok and calendar_ok:
        logger.info("\n🎉 所有测试通过！系统可以使用了！")
        logger.info("\n启动命令: python app.py")
    else:
        logger.info("\n⚠️  部分测试失败，请检查错误信息")

if __name__ == "__main__":
    asyncio.run(main())