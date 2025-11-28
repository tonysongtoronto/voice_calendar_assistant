import logging
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import json

from calendar_bot import CalendarBot
from voice_handler import VoiceHandler
from nlp_parser import NLPParser

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(title="语音日程助手", version="2.0.0")

# 全局变量
calendar_bot: CalendarBot = None
voice_handler: VoiceHandler = None
nlp_parser: NLPParser = None

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化所有模块"""
    global calendar_bot, voice_handler, nlp_parser
    
    logger.info("=" * 80)
    logger.info("🚀 应用启动中...")
    logger.info("=" * 80)
    
    # 初始化 NLP 解析器
    logger.info("0️⃣ 初始化 NLP 解析器...")
    nlp_parser = NLPParser()
    logger.info("✅ NLP 解析器初始化完成")
    
    # 初始化语音处理器
    logger.info("1️⃣ 初始化语音处理器...")
    voice_handler = VoiceHandler()
    logger.info("✅ 语音处理器初始化完成")
    
    # 初始化日历机器人
    logger.info("2️⃣ 初始化 Calendar Bot...")
    calendar_bot = CalendarBot()
    await calendar_bot.initialize()
    logger.info("✅ Calendar Bot 初始化完成")
    
    logger.info("=" * 80)
    logger.info("✅ 所有模块初始化完成，服务器就绪！")
    logger.info("🌐 访问地址: http://localhost:8000")
    logger.info("=" * 80)

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    global calendar_bot
    if calendar_bot:
        logger.info("🔚 应用关闭，清理 Calendar Bot 资源...")
        await calendar_bot.close()
        logger.info("✅ Calendar Bot 已关闭")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """返回主页面HTML"""
    html_file = Path("index.html")
    
    if html_file.exists():
        logger.info("📄 正在加载 index.html...")
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
            logger.info("✅ index.html 加载成功")
            return HTMLResponse(content=content)
    else:
        logger.error("❌ 找不到 index.html 文件！")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>错误</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .error-box {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                    text-align: center;
                }}
                h1 {{ color: #f44336; }}
                p {{ color: #666; margin: 10px 0; }}
                code {{ 
                    background: #f5f5f5; 
                    padding: 2px 8px; 
                    border-radius: 3px;
                    color: #d32f2f;
                }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>❌ 找不到 index.html</h1>
                <p>请在以下位置创建 <code>index.html</code> 文件：</p>
                <p><code>{html_file.absolute()}</code></p>
                <p style="margin-top: 20px;">当前工作目录：<code>{Path.cwd()}</code></p>
            </div>
        </body>
        </html>
        """, status_code=404)

@app.get("/api/health")
async def health_check():
    """健康检查API"""
    return {
        "status": "running",
        "calendar_bot_initialized": calendar_bot is not None and calendar_bot.is_logged_in,
        "working_directory": str(Path.cwd()),
        "index_html_exists": Path("index.html").exists(),
        "timestamp": datetime.now().isoformat()
    }

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket):
    """WebSocket 语音对话端点 - 包含时间冲突检查"""
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🔌 WebSocket 连接已建立 from {client_ip}")
    
    try:
        # 发送欢迎消息并播放语音
        welcome_text = "您好！我是您的语音日程助手。请点击按钮开始录音，然后告诉我您的日程安排。"
        
        logger.info("=" * 60)
        logger.info("🎤 开始生成欢迎语音...")
        logger.info(f"欢迎文本: {welcome_text}")
        
        try:
            welcome_audio = await voice_handler.text_to_speech(welcome_text)
            
            if welcome_audio:
                logger.info(f"✅ 欢迎语音生成成功，长度: {len(welcome_audio)} 字符")
                
                # 发送带语音的欢迎消息
                message = {
                    "type": "audio_response",
                    "audio": welcome_audio,
                    "text": welcome_text,
                    "success": True
                }
                
                await websocket.send_json(message)
                logger.info("✅ 欢迎消息已发送到客户端")
                logger.info("=" * 60)
            else:
                logger.warning("⚠️ 欢迎语音生成返回空值")
                await websocket.send_json({
                    "type": "status",
                    "message": welcome_text,
                    "success": True
                })
        except Exception as e:
            logger.error(f"❌ 生成或发送欢迎语音时出错: {e}", exc_info=True)
            await websocket.send_json({
                "type": "status",
                "message": welcome_text,
                "success": True
            })
        
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "audio_input":
                try:
                    logger.info("📝 收到音频数据，开始处理...")
                    
                    # 1. 接收音频数据
                    audio_hex = data.get("audio")
                    audio_bytes = bytes.fromhex(audio_hex)
                    
                    logger.info(f"📝 音频数据大小: {len(audio_bytes)} 字节")
                    
                    # 2. 语音识别
                    logger.info("🎧 开始语音识别...")
                    recognized_text = await voice_handler.speech_to_text(audio_bytes)
                    
                    if not recognized_text:
                        error_text = "抱歉，我没有听清楚，请再说一次。"
                        error_audio = await voice_handler.text_to_speech(error_text)
                        
                        await websocket.send_json({
                            "type": "error",
                            "message": error_text,
                            "audio": error_audio if error_audio else None,
                            "success": False
                        })
                        continue
                    
                    logger.info(f"🎤 识别的文字: {recognized_text}")
                    
                    # 发送识别结果到前端显示
                    await websocket.send_json({
                        "type": "transcript",
                        "text": recognized_text
                    })
                    
                    # 3. NLP 解析日程信息
                    logger.info("📋 开始 NLP 解析...")
                    schedule_info = nlp_parser.parse(recognized_text)
                    
                    # 检查解析是否失败
                    if not schedule_info or not schedule_info.get('success', True):
                        error_msg = schedule_info.get('error', '无法理解您的日程安排') if isinstance(schedule_info, dict) else "解析失败"
                        logger.error(f"❌ NLP解析失败: {error_msg}")
                        
                        error_audio = await voice_handler.text_to_speech(error_msg)
                        
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg,
                            "audio": error_audio if error_audio else None,
                            "success": False
                        })
                        continue
                    
                    logger.info(f"📋 NLP解析成功: {schedule_info}")
                    
                    # 4. 检查时间冲突
                    logger.info("🔍 开始检查时间冲突...")
                    await websocket.send_json({
                        "type": "status",
                        "message": "正在检查日程冲突...",
                        "success": True
                    })
                    
                    conflict_result = await calendar_bot.check_time_conflict(
                        schedule_info['start_time'],
                        schedule_info['end_time']
                    )
                    
                    if conflict_result.get('has_conflict'):
                        logger.warning("⚠️ 检测到时间冲突！")
                        conflicting_events = conflict_result['conflicting_events']
                        
                        # 构建冲突提示
                        conflict_text = "⚠️ 检测到时间冲突！您已有以下安排："
                        for i, event in enumerate(conflicting_events[:3], 1):  # 最多显示3个
                            conflict_text += f"{i}. {event['start']}到{event['end']}；"
                        
                        if len(conflicting_events) > 3:
                            conflict_text += f"等{len(conflicting_events)}个日程。"
                        
                        conflict_text += "请调整时间或取消原有日程。"
                        
                        # 生成警告语音
                        conflict_audio = await voice_handler.text_to_speech(conflict_text)
                        
                        # 发送冲突警告
                        await websocket.send_json({
                            "type": "error",
                            "message": conflict_text,
                            "audio": conflict_audio if conflict_audio else None,
                            "success": False
                        })
                        
                        # 继续等待用户输入，不创建日程
                        continue
                    
                    logger.info("✅ 无时间冲突，继续创建日程")
                    
                    # 5. 创建日程
                    logger.info("📅 开始创建 Google Calendar 日程...")
                    await websocket.send_json({
                        "type": "status",
                        "message": "正在创建日程安排...",
                        "success": True
                    })
                    
                    result = await calendar_bot.create_event(
                        title=schedule_info['title'],
                        start_time=schedule_info['start_time'],
                        end_time=schedule_info['end_time']
                    )
                    
                    # 6. 生成响应文字和语音
                    if result['success']:
                        # 格式化日期和时间
                        start_dt = schedule_info['start_time']
                        end_dt = schedule_info['end_time']
                        
                        # 智能日期显示
                        today = datetime.now().date()
                        date_str = ""
                        if start_dt.date() == today:
                            date_str = "今天"
                        elif start_dt.date() == today + timedelta(days=1):
                            date_str = "明天"
                        elif start_dt.date() == today + timedelta(days=2):
                            date_str = "后天"
                        else:
                            date_str = f"{start_dt.month}月{start_dt.day}日"
                        
                        time_str = f"{start_dt.hour}点{start_dt.minute:02d}分到{end_dt.hour}点{end_dt.minute:02d}分"
                        
                        response_text = f"好的！我已经成功为您创建了日程：{schedule_info['title']}，时间：{date_str}{time_str}。还有其他需要安排的吗？"
                        logger.info(f"✅ 日程创建成功: {schedule_info['title']}")
                    else:
                        response_text = f"抱歉，创建日程时遇到了问题：{result.get('error', '未知错误')}。请稍后重试。"
                        logger.error(f"❌ 日程创建失败: {result.get('error')}")
                    
                    # 7. 生成确认语音
                    logger.info("🎤 生成确认语音...")
                    audio_base64 = await voice_handler.text_to_speech(response_text)
                    
                    # 8. 发送响应到前端
                    response_message = {
                        "type": "audio_response",
                        "text": response_text,
                        "success": result['success']
                    }
                    
                    if audio_base64:
                        response_message["audio"] = audio_base64
                        logger.info("✅ 确认语音已生成")
                    else:
                        logger.warning("⚠️ 确认语音生成失败")
                    
                    await websocket.send_json(response_message)
                    logger.info("=" * 60)
                    
                except Exception as e:
                    logger.error(f"❌ 处理音频时出错: {e}", exc_info=True)
                    error_msg = f"处理失败: {str(e)}"
                    error_audio = await voice_handler.text_to_speech("抱歉，处理过程中出现了错误，请重试。")
                    
                    await websocket.send_json({
                        "type": "error",
                        "message": error_msg,
                        "audio": error_audio if error_audio else None,
                        "success": False
                    })
            
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket 连接已断开")
    except Exception as e:
        logger.error(f"❌ WebSocket 错误: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": "连接错误，请刷新页面重试",
                "success": False
            })
        except:
            pass

@app.post("/api/process_voice")
async def process_voice(audio: UploadFile = File(...)):
    """处理语音输入并创建日程（REST API版本）- 包含时间冲突检查"""
    try:
        logger.info(f"📝 收到音频文件: {audio.filename}")
        
        # 1. 读取音频文件
        audio_bytes = await audio.read()
        logger.info(f"📝 音频文件大小: {len(audio_bytes)} 字节")
        
        # 2. 语音识别
        logger.info("🎧 开始语音识别...")
        recognized_text = await voice_handler.speech_to_text(audio_bytes)
        
        if not recognized_text:
            return {
                "success": False,
                "message": "语音识别失败，请重试",
                "error_type": "speech_recognition_failed"
            }
        
        logger.info(f"🎤 识别的文字: {recognized_text}")
        
        # 3. NLP 解析
        logger.info("📋 使用 NLP 解析日程信息...")
        schedule_info = nlp_parser.parse(recognized_text)
        
        if not schedule_info or not schedule_info.get('success', True):
            error_msg = schedule_info.get('error', '无法理解您的日程安排') if isinstance(schedule_info, dict) else "解析失败"
            return {
                "success": False,
                "message": error_msg,
                "recognized_text": recognized_text,
                "error_type": "nlp_parse_failed"
            }
        
        logger.info(f"📋 解析的日程信息: {schedule_info}")
        
        # 4. 检查时间冲突
        logger.info("🔍 检查时间冲突...")
        conflict_result = await calendar_bot.check_time_conflict(
            schedule_info['start_time'],
            schedule_info['end_time']
        )
        
        if conflict_result.get('has_conflict'):
            conflicting_events = conflict_result['conflicting_events']
            conflict_text = "检测到时间冲突："
            for event in conflicting_events:
                conflict_text += f"{event['start']}到{event['end']}；"
            
            return {
                "success": False,
                "message": conflict_text,
                "recognized_text": recognized_text,
                "conflicting_events": conflicting_events,
                "error_type": "time_conflict"
            }
        
        # 5. 创建日程
        logger.info("📅 创建日程...")
        result = await calendar_bot.create_event(
            title=schedule_info['title'],
            start_time=schedule_info['start_time'],
            end_time=schedule_info['end_time']
        )
        
        # 6. 生成响应
        if result['success']:
            start_dt = schedule_info['start_time']
            end_dt = schedule_info['end_time']
            
            # 日期格式化
            today = datetime.now().date()
            if start_dt.date() == today:
                date_str = "今天"
            elif start_dt.date() == today + timedelta(days=1):
                date_str = "明天"
            else:
                date_str = f"{start_dt.month}月{start_dt.day}日"
            
            time_str = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
            response_text = f"✅ 已成功创建日程：{schedule_info['title']}，时间：{date_str} {time_str}"
            logger.info(f"✅ {response_text}")
        else:
            response_text = f"❌ 创建日程失败：{result.get('error', '未知错误')}"
            logger.error(f"❌ {response_text}")
        
        # 7. 生成语音响应
        audio_base64 = await voice_handler.text_to_speech(response_text)
        
        return {
            "success": result['success'],
            "message": response_text,
            "recognized_text": recognized_text,
            "audio": audio_base64 if audio_base64 else None,
            "details": result,
            "error_type": None
        }
        
    except Exception as e:
        logger.error(f"❌ 处理请求时出错: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"处理失败: {str(e)}",
            "error_type": "server_error"
        }

@app.get("/api/test")
async def test_components():
    """测试所有组件状态"""
    try:
        # 测试语音处理
        test_audio = await voice_handler.text_to_speech("测试语音合成")
        tts_working = bool(test_audio)
        
        # 测试NLP解析
        test_parse = nlp_parser.parse("明天下午2点开会")
        nlp_working = bool(test_parse and test_parse.get('success', True))
        
        # 测试日历连接
        calendar_working = calendar_bot.is_logged_in if calendar_bot else False
        
        return {
            "status": "healthy" if all([tts_working, nlp_working, calendar_working]) else "degraded",
            "components": {
                "voice_handler": {"working": tts_working},
                "nlp_parser": {"working": nlp_working},
                "calendar_bot": {"working": calendar_working, "logged_in": calendar_working}
            },
            "test_audio_length": len(test_audio) if test_audio else 0
        }
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    # 运行服务器
    logger.info("🚀 启动服务器...")
    logger.info(f"📁 当前工作目录: {Path.cwd()}")
    logger.info(f"📄 index.html 存在: {Path('index.html').exists()}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )