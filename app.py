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
from nlp_parser import NLPParser  # 导入 NLP 解析器

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# ✅ 全局变量
calendar_bot: CalendarBot = None
voice_handler: VoiceHandler = None
nlp_parser: NLPParser = None

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
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
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>错误</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .error-box {
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                    text-align: center;
                }
                h1 { color: #f44336; }
                p { color: #666; margin: 10px 0; }
                code { 
                    background: #f5f5f5; 
                    padding: 2px 8px; 
                    border-radius: 3px;
                    color: #d32f2f;
                }
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>❌ 找不到 index.html</h1>
                <p>请在以下位置创建 <code>index.html</code> 文件：</p>
                <p><code>""" + str(Path.cwd() / "index.html") + """</code></p>
                <p style="margin-top: 20px;">当前工作目录：<code>""" + str(Path.cwd()) + """</code></p>
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
        "index_html_exists": Path("index.html").exists()
    }

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket):
    """WebSocket 语音对话端点"""
    await websocket.accept()
    logger.info("🔌 WebSocket 连接已建立")
    
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
                # 语音生成失败，只发送文字
                await websocket.send_json({
                    "type": "status",
                    "message": welcome_text
                })
                logger.warning("⚠️ 只发送了欢迎文字，没有音频")
        except Exception as e:
            logger.error(f"❌ 生成或发送欢迎语音时出错: {e}", exc_info=True)
            # 至少发送文字消息
            await websocket.send_json({
                "type": "status",
                "message": welcome_text
            })
        
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "audio_input":
                try:
                    # 1. 接收音频数据
                    audio_hex = data.get("audio")
                    audio_bytes = bytes.fromhex(audio_hex)
                    
                    logger.info(f"📝 收到音频数据，大小: {len(audio_bytes)} 字节")
                    
                    # 2. 语音识别
                    logger.info("🎧 开始语音识别...")
                    recognized_text = await voice_handler.speech_to_text(audio_bytes)
                    
                    if not recognized_text:
                        # 识别失败
                        error_text = "抱歉，我没有听清楚，请再说一次。"
                        error_audio = await voice_handler.text_to_speech(error_text)
                        
                        await websocket.send_json({
                            "type": "error",
                            "message": error_text,
                            "audio": error_audio if error_audio else None
                        })
                        continue
                    
                    logger.info(f"🎤 识别的文字: {recognized_text}")
                    
                    # 发送识别结果
                    await websocket.send_json({
                        "type": "transcript",
                        "text": recognized_text
                    })
                    
                    # 3. NLP 解析日程信息
                    logger.info("📋 使用 NLP 解析日程信息...")
                    schedule_info = nlp_parser.parse(recognized_text)
                    
                    if not schedule_info:
                        error_text = "抱歉，我无法理解您的日程安排。请尝试说：明天下午2点到3点，团队会议。"
                        error_audio = await voice_handler.text_to_speech(error_text)
                        
                        await websocket.send_json({
                            "type": "error",
                            "message": error_text,
                            "audio": error_audio if error_audio else None
                        })
                        continue
                    
                    logger.info(f"📋 解析的日程信息: {schedule_info}")
                    
                    # 4. 创建日程
                    logger.info("📅 开始创建日程...")
                    result = await calendar_bot.create_event(
                        title=schedule_info['title'],
                        start_time=schedule_info['start_time'],
                        end_time=schedule_info['end_time']
                    )
                    
                    # 5. 生成响应文字和语音（使用解析的实际时间）
                    if result['success']:
                        # 格式化日期和时间 - 避免使用中文字符的 strftime
                        start_dt = schedule_info['start_time']
                        end_dt = schedule_info['end_time']
                        
                        # 手动构建日期字符串，避免编码问题
                        date_str = f"{start_dt.year}年{start_dt.month}月{start_dt.day}日"
                        time_str = f"{start_dt.hour}点{start_dt.minute:02d}分到{end_dt.hour}点{end_dt.minute:02d}分"
                        
                        response_text = f"好的！我已经成功为您创建了日程：{schedule_info['title']}，时间是{date_str}{time_str}。还有其他需要安排的吗？"
                        logger.info(f"✅ 日程创建成功")
                    else:
                        response_text = f"抱歉，创建日程时遇到了问题：{result.get('error', '未知错误')}。请稍后重试。"
                        logger.error(f"❌ 日程创建失败: {result.get('error')}")
                    
                    # 6. 生成确认语音
                    logger.info("🎤 生成确认语音...")
                    audio_base64 = await voice_handler.text_to_speech(response_text)
                    
                    # 7. 发送响应
                    response_message = {
                        "type": "audio_response",
                        "text": response_text,
                        "success": result['success']
                    }
                    
                    if audio_base64:
                        response_message["audio"] = audio_base64
                        logger.info("✅ 确认语音已生成")
                    else:
                        logger.warning("⚠️ 确认语音生成失败，只发送文字")
                    
                    await websocket.send_json(response_message)
                    
                except Exception as e:
                    logger.error(f"❌ 处理音频时出错: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"处理失败: {str(e)}"
                    })
            
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket 连接已断开")
    except Exception as e:
        logger.error(f"❌ WebSocket 错误: {e}", exc_info=True)

@app.post("/api/process_voice")
async def process_voice(audio: UploadFile = File(...)):
    """处理语音输入并创建日程（REST API版本）"""
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
                "message": "语音识别失败，请重试"
            }
        
        logger.info(f"🎤 识别的文字: {recognized_text}")
        
        # 3. NLP 解析
        logger.info("📋 使用 NLP 解析日程信息...")
        schedule_info = nlp_parser.parse(recognized_text)
        
        if not schedule_info:
            return {
                "success": False,
                "message": "无法理解您的日程安排，请重试"
            }
        
        logger.info(f"📋 解析的日程信息: {schedule_info}")
        
        # 4. 创建日程
        logger.info("📅 创建日程...")
        result = await calendar_bot.create_event(
            title=schedule_info['title'],
            start_time=schedule_info['start_time'],
            end_time=schedule_info['end_time']
        )
        
        # 5. 生成响应
        if result['success']:
            start_dt = schedule_info['start_time']
            end_dt = schedule_info['end_time']
            # 手动构建日期和时间字符串，避免编码问题
            date_str = f"{start_dt.year}年{start_dt.month}月{start_dt.day}日"
            time_str = f"{start_dt.hour}:{start_dt.minute:02d} - {end_dt.hour}:{end_dt.minute:02d}"
            response_text = f"✅ 已成功创建日程：{schedule_info['title']}，时间：{date_str} {time_str}"
            logger.info(response_text)
        else:
            response_text = f"❌ 创建日程失败：{result.get('error', '未知错误')}"
            logger.error(response_text)
        
        # 6. 生成语音响应
        audio_base64 = await voice_handler.text_to_speech(response_text)
        
        return {
            "success": result['success'],
            "message": response_text,
            "recognized_text": recognized_text,
            "audio": audio_base64 if audio_base64 else None,
            "details": result
        }
        
    except Exception as e:
        logger.error(f"❌ 处理请求时出错: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"处理失败: {str(e)}"
        }

if __name__ == "__main__":
    # 运行服务器
    logger.info("🚀 启动服务器...")
    logger.info(f"📁 当前工作目录: {Path.cwd()}")
    logger.info(f"📄 index.html 存在: {Path('index.html').exists()}")
    uvicorn.run(app, host="0.0.0.0", port=8000)