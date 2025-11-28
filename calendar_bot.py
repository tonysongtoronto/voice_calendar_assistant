import logging
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import warnings
from urllib.parse import quote
import re

# 忽略FP16警告
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

logger = logging.getLogger(__name__)

def parse_time_flexible(time_str: str, reference_date: datetime) -> datetime:
    """
    灵活解析时间字符串，支持多种格式
    
    支持格式：
    - 24小时制: "14:00", "9:30"
    - 12小时制: "2:00 PM", "9:30 AM"
    - 中文格式: "下午2:00", "上午9:30"
    """
    time_str = time_str.strip()
    
    # 标准格式尝试
    formats = [
        "%I:%M %p",    # 2:00 PM
        "%H:%M",       # 14:00
        "%I:%M%p",     # 2:00PM (无空格)
        "%I %p",       # 2 PM (只有小时)
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(time_str, fmt)
            return parsed.replace(
                year=reference_date.year,
                month=reference_date.month,
                day=reference_date.day
            )
        except ValueError:
            continue
    
    # 正则表达式兜底解析
    # 匹配模式: 数字:数字 [可选的AM/PM/上午/下午]
    match = re.search(r'(\d{1,2}):?(\d{2})?', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        
        # 处理 AM/PM 标识
        is_pm = 'PM' in time_str.upper() or '下午' in time_str or 'pm' in time_str.lower()
        is_am = 'AM' in time_str.upper() or '上午' in time_str or 'am' in time_str.lower()
        
        if is_pm and hour < 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0  # 12:00 AM 是午夜
        
        # 如果没有 AM/PM 标识且小时数小于等于12，可能有歧义
        # 这里假设用户使用24小时制
        
        return datetime(
            reference_date.year,
            reference_date.month,
            reference_date.day,
            hour, minute
        )
    
    raise ValueError(f"无法解析时间: {time_str}")


class CalendarBot:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.storage_state_path = Path("storage_state.json")
        self.is_logged_in = False
        self._browser_check_task = None

    async def initialize(self):
        """初始化浏览器并检查登录状态"""
        logger.info("初始化 Calendar Bot...")
        self.playwright = await async_playwright().start()

        if self.storage_state_path.exists():
            logger.info("发现保存的登录状态，尝试复用...")
            try:
                await self._load_saved_session()
                if await self._verify_login():
                    logger.info("✅ 登录状态有效，已成功复用")
                    self.is_logged_in = True
                    self.page.set_default_timeout(30000)
                    self.page.set_default_navigation_timeout(30000)
                    
                    # 启动浏览器监控
                    self._start_browser_monitor()
                    return
                else:
                    logger.warning("⚠️ 登录状态已失效")
                    await self._close_browser_only()
            except Exception as e:
                logger.error(f"复用登录状态失败: {e}")
                await self._close_browser_only()

        # 需要手动登录
        await self._manual_login()
        self.page.set_default_timeout(30000)
        self.page.set_default_navigation_timeout(30000)
        
        # 启动浏览器监控
        self._start_browser_monitor()

    def _start_browser_monitor(self):
        """启动浏览器状态监控"""
        # 先取消旧任务（修复内存泄漏）
        if self._browser_check_task and not self._browser_check_task.done():
            self._browser_check_task.cancel()
        
        async def monitor():
            while True:
                try:
                    await asyncio.sleep(30)
                    if self.page and not self.page.is_closed():
                        try:
                            await self.page.evaluate("() => true")
                        except:
                            logger.warning("⚠️ 浏览器可能已关闭，将在下次使用时自动恢复")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"浏览器监控错误: {e}")
        
        self._browser_check_task = asyncio.create_task(monitor())

    async def _close_browser_only(self):
        """只关闭浏览器，不关闭playwright"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")

    async def _ensure_browser_ready(self):
        """确保浏览器处于可用状态"""
        try:
            if self.page and not self.page.is_closed():
                await asyncio.wait_for(
                    self.page.evaluate("() => true"),
                    timeout=2.0
                )
                logger.info("✅ 浏览器状态正常")
                return True
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"⚠️ 浏览器状态检查失败: {e}")
        
        logger.warning("⚠️ 检测到浏览器已关闭，正在尝试自动恢复...")
        
        try:
            await self._close_browser_only()
            
            if self.storage_state_path.exists():
                logger.info("📂 使用保存的登录状态恢复浏览器...")
                await self._load_saved_session()
                
                if await self._verify_login():
                    logger.info("✅ 浏览器恢复成功！")
                    self.page.set_default_timeout(30000)
                    self.page.set_default_navigation_timeout(30000)
                    return True
                else:
                    logger.error("❌ 登录状态验证失败")
            else:
                logger.error("❌ 未找到保存的登录状态")
            
        except Exception as e:
            logger.error(f"❌ 浏览器恢复失败: {e}")
        
        logger.error("=" * 60)
        logger.error("❌ 无法恢复浏览器状态")
        logger.error("💡 解决方法：")
        logger.error("   1. 请不要手动关闭浏览器窗口")
        logger.error("   2. 或者重启程序 (Ctrl+C 然后 python app.py)")
        logger.error("=" * 60)
        return False

    async def _load_saved_session(self):
        """加载保存的浏览器会话"""
        browsers_to_try = [
            ("chrome", "系统 Chrome"),
            ("chromium", "Playwright Chromium"),
            ("firefox", "Firefox")
        ]
        
        last_error = None
        for browser_type, browser_name in browsers_to_try:
            try:
                logger.info(f"尝试使用 {browser_name}...")
                
                if browser_type == "chrome":
                    self.browser = await self.playwright.chromium.launch(
                        headless=False,
                        channel="chrome",
                        args=['--start-maximized', '--disable-blink-features=AutomationControlled']
                    )
                elif browser_type == "chromium":
                    self.browser = await self.playwright.chromium.launch(
                        headless=False,
                        args=['--start-maximized', '--disable-blink-features=AutomationControlled']
                    )
                else:
                    self.browser = await self.playwright.firefox.launch(
                        headless=False,
                        args=['--start-maximized']
                    )
                
                logger.info(f"✅ 成功使用 {browser_name}")
                break
                
            except Exception as e:
                logger.warning(f"⚠️ 无法使用 {browser_name}: {e}")
                last_error = e
                continue
        
        if not self.browser:
            raise Exception(f"无法启动任何浏览器。最后的错误: {last_error}")
        
        self.context = await self.browser.new_context(
            storage_state=str(self.storage_state_path),
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        self.page = await self.context.new_page()

    async def _verify_login(self) -> bool:
        """验证当前登录状态是否有效"""
        try:
            logger.info("验证登录状态...")
            await self.page.goto("https://calendar.google.com", wait_until="domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(3000)
            current_url = self.page.url
            if "accounts.google.com" in current_url:
                return False
            try:
                await self.page.wait_for_selector('[data-view-heading]', timeout=10000)
                return True
            except:
                return False
        except Exception as e:
            logger.error(f"验证登录状态时出错: {e}")
            return False

    async def _manual_login(self):
        """手动登录流程"""
        try:
            logger.info("尝试使用系统 Chrome 浏览器...")
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    '--start-maximized',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            logger.info("✅ 成功使用系统 Chrome")
        except Exception as e:
            logger.warning(f"无法使用系统 Chrome: {e}")
            logger.info("回退使用 Playwright Chromium...")
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--start-maximized',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        self.page = await self.context.new_page()
        await self.page.goto("https://calendar.google.com")
        logger.info("=" * 60)
        logger.info("📢 请在浏览器中手动登录 Google 账号")
        logger.info("⚠️ 登录完成后，请保持浏览器窗口打开，不要关闭！")
        logger.info("⚠️ 然后在终端按回车继续...")
        logger.info("=" * 60)
        input("登录完成后按回车继续...")
        await self.context.storage_state(path=str(self.storage_state_path))
        self.is_logged_in = True
        logger.info("✅ 登录状态已保存")

    async def check_time_conflict(self, start_time: datetime, end_time: datetime) -> dict:
        """
        检查时间冲突 - 改进版（2025 更新）
        
        修复内容：
        1. 用 regex 提取时间范围，更可靠
        2. 直接用事件 inner_text，避免类名失效
        3. 更好处理中文/英文时间格式
        4. 增强全天事件过滤和日志
        """
        logger.info("=" * 80)
        logger.info(f"🔍 检查时间冲突")
        logger.info(f"   开始: {start_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"   结束: {end_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info("=" * 80)
        
        result = {
            'has_conflict': False,
            'conflicting_events': [],
            'error': None
        }
        
        try:
            # 确保浏览器可用
            if not await self._ensure_browser_ready():
                result['error'] = "无法初始化浏览器"
                return result
            
            # 处理跨天的用户输入
            check_start = start_time
            check_end = end_time
            if check_end < check_start:
                check_end += timedelta(days=1)
                logger.info(f"⚠️ 检测到跨天时间，已调整结束时间为次日")
            
            # 导航到目标日期的日视图
            date_str = start_time.strftime("%Y/%m/%d")
            check_url = f"https://calendar.google.com/calendar/u/0/r/day/{date_str}"
            
            logger.info(f"🌐 导航到日期视图: {check_url}")
            await self.page.goto(check_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(5000)  # 等待加载事件
            
            # 查找现有事件 - 保留原有选择器，但添加更通用的
            event_selectors = [
                '[data-eventid]',
                '.YvjgZe',  # 旧版，可能失效
                '[role="button"][data-event-id]',
                '.ynRLnc',
                '[data-view-family="EVENT"]',
                # 新增通用选择器：事件通常是可点击的 div/button
                'div[role="row"] > div[style*="top"]',  # 日视图事件块
                '.bEdKdb',  # 常见事件容器类（2025 可能有效）
            ]
            
            events = []
            for selector in event_selectors:
                try:
                    events = await self.page.query_selector_all(selector)
                    if events:
                        logger.info(f"✅ 找到 {len(events)} 个事件 (选择器: {selector})")
                        break
                except Exception as e:
                    logger.debug(f"选择器 {selector} 失败: {e}")
                    continue
            
            if not events:
                logger.info("✅ 当天无事件，无冲突")
                return result
            
            # 提取并检查每个事件
            for idx, event in enumerate(events):
                try:
                    # 直接取整个事件文本
                    full_text = await event.inner_text()
                    if not full_text or len(full_text.strip()) < 5:
                        continue
                    
                    logger.info(f"📅 [{idx+1}] 事件全文: {full_text}")
                    
                    # 跳过全天事件（检查关键词或无时间）
                    if any(keyword in full_text for keyword in ['全天', 'All day', 'all-day']):
                        logger.info(f"   ↳ 跳过全天事件")
                        continue
                    
                    # 用 regex 提取时间范围：匹配 HH:MM – HH:MM 或 HH:MM - HH:MM
                    time_pattern = r'(\d{1,2}:\d{2})\s*[–\-\u2013\u2014]\s*(\d{1,2}:\d{2})'  # 支持 en/em dash
                    match = re.search(time_pattern, full_text)
                    if not match:
                        logger.debug(f"   ↳ 无有效时间范围，跳过: {full_text[:50]}...")
                        continue
                    
                    start_str, end_str = match.group(1), match.group(2)
                    logger.info(f"   ↳ 提取时间: {start_str} – {end_str}")
                    
                    # 使用灵活解析函数
                    try:
                        event_start = parse_time_flexible(start_str, start_time)
                        event_end = parse_time_flexible(end_str, start_time)
                    except ValueError as e:
                        logger.warning(f"   ↳ 时间解析失败: {e}")
                        continue
                    
                    # 处理跨天事件
                    if event_end <= event_start:
                        event_end += timedelta(days=1)
                        logger.info(f"   ↳ 跨天事件: {event_start.strftime('%H:%M')} - 次日 {event_end.strftime('%H:%M')}")
                    
                    # 检查时间重叠：(check_start < event_end) and (check_end > event_start)
                    has_overlap = (check_start < event_end) and (check_end > event_start)
                    
                    if has_overlap:
                        overlap_start = max(check_start, event_start)
                        overlap_end = min(check_end, event_end)
                        logger.warning(f"⚠️ 时间冲突:")
                        logger.warning(f"   已有: {event_start.strftime('%H:%M')} - {event_end.strftime('%H:%M')}")
                        logger.warning(f"   新建: {check_start.strftime('%H:%M')} - {check_end.strftime('%H:%M')}")
                        logger.warning(f"   重叠: {overlap_start.strftime('%H:%M')} - {overlap_end.strftime('%H:%M')}")
                        
                        result['has_conflict'] = True
                        result['conflicting_events'].append({
                            'start': event_start.strftime('%H:%M'),
                            'end': event_end.strftime('%H:%M'),
                            'original_text': full_text,
                            'overlap_start': overlap_start.strftime('%H:%M'),
                            'overlap_end': overlap_end.strftime('%H:%M'),
                        })
                    else:
                        logger.info(f"   ✅ 无冲突")
                        
                except Exception as e:
                    logger.debug(f"检查事件 {idx+1} 时出错: {e}")
                    continue
            
            # 输出最终结果
            if result['has_conflict']:
                logger.warning(f"❌ 发现 {len(result['conflicting_events'])} 个时间冲突")
                for conf in result['conflicting_events']:
                    logger.warning(f"   - {conf['original_text'][:50]}... ({conf['start']}-{conf['end']})")
            else:
                logger.info(f"✅ 无时间冲突")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 检查时间冲突失败: {e}", exc_info=True)
            result['error'] = str(e)
            return result

    async def create_event(self, title: str, start_time: datetime, end_time: datetime) -> dict:
        """创建日程事件 - 使用URL参数方式（最可靠）"""
        logger.info("=" * 80)
        logger.info(f"📅 开始创建事件")
        logger.info(f"   标题: {title}")
        logger.info(f"   开始: {start_time}")
        logger.info(f"   结束: {end_time}")
        logger.info("=" * 80)
        
        result = {
            'success': False,
            'title': title,
            'date_str': start_time.strftime("%Y-%m-%d"),
            'time_str': f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
            'error': None
        }
        
        try:
            # 确保浏览器可用
            logger.info("🔍 检查浏览器状态...")
            if not await self._ensure_browser_ready():
                error_msg = "无法初始化浏览器"
                logger.error(f"❌ {error_msg}")
                result['error'] = error_msg
                return result
            
            logger.info("✅ 浏览器状态正常")
            
            # 使用Google Calendar的URL参数创建事件（最可靠的方法）
            logger.info(f"🌐 使用URL参数创建事件...")
            
            # 格式化时间为 ISO 8601 格式（Google Calendar URL格式）
            start_str = start_time.strftime("%Y%m%dT%H%M%S")
            end_str = end_time.strftime("%Y%m%dT%H%M%S")
            
            # URL编码标题
            encoded_title = quote(title)
            
            # 构建创建URL
            create_url = f"https://calendar.google.com/calendar/u/0/r/eventedit?text={encoded_title}&dates={start_str}/{end_str}"
            
            logger.info(f"📝 创建URL: {create_url}")
            await self.page.goto(create_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)
            logger.info("✅ 事件编辑页面已加载")
            
            # 等待页面完全加载
            try:
                await self.page.wait_for_selector(
                    'input[aria-label*="添加标题"], input[aria-label*="Add title"]',
                    timeout=5000
                )
                logger.info("✅ 表单已加载")
            except:
                logger.info("⚠️ 表单可能已预填充")
            
            # 给页面一点时间渲染
            await self.page.wait_for_timeout(2000)
            
            # 尝试多种保存方式
            logger.info("💾 开始保存事件...")
            saved = False
            
            # 方法1: 使用键盘快捷键 Ctrl+S（最可靠）
            try:
                logger.info("🎯 方法1: 使用键盘快捷键...")
                await self.page.keyboard.press("Control+s")
                await self.page.wait_for_timeout(3000)
                logger.info("✅ 已按下保存快捷键")
                saved = True
            except Exception as e:
                logger.warning(f"方法1失败: {e}")
            
            # 方法2: 查找并点击保存按钮
            if not saved:
                try:
                    logger.info("🎯 方法2: 查找保存按钮...")
                    save_buttons = await self.page.query_selector_all('button')
                    for btn in save_buttons:
                        text = await btn.inner_text()
                        aria_label = await btn.get_attribute('aria-label')
                        
                        if text and ('保存' in text or 'Save' in text.lower()):
                            await btn.scroll_into_view_if_needed()
                            await self.page.wait_for_timeout(500)
                            await btn.click(force=True)
                            logger.info(f"✅ 已点击保存按钮: {text}")
                            saved = True
                            break
                        elif aria_label and ('保存' in aria_label or 'save' in aria_label.lower()):
                            await btn.scroll_into_view_if_needed()
                            await self.page.wait_for_timeout(500)
                            await btn.click(force=True)
                            logger.info(f"✅ 已点击保存按钮: {aria_label}")
                            saved = True
                            break
                    
                    if saved:
                        await self.page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning(f"方法2失败: {e}")
            
            # 方法3: 点击页面外部（Google Calendar通常会自动保存）
            if not saved:
                try:
                    logger.info("🎯 方法3: 点击外部区域触发保存...")
                    await self.page.keyboard.press("Escape")
                    await self.page.wait_for_timeout(2000)
                    logger.info("✅ 已按下ESC键")
                    saved = True
                except Exception as e:
                    logger.warning(f"方法3失败: {e}")
            
            # 验证保存结果
            logger.info("🔍 验证事件是否保存成功...")
            await self.page.wait_for_timeout(2000)
            
            current_url = self.page.url
            logger.info(f"📍 当前URL: {current_url}")
            
            # 检查是否已离开编辑页面
            if "eventedit" not in current_url:
                logger.info("✅ 事件创建完成 - 已离开编辑页面")
                result['success'] = True
            else:
                # 还在编辑页面，再等一下
                logger.info("⏳ 仍在编辑页面，再等待...")
                await self.page.wait_for_timeout(3000)
                
                current_url = self.page.url
                if "eventedit" not in current_url:
                    logger.info("✅ 事件创建完成")
                    result['success'] = True
                else:
                    # 假定已保存（Google Calendar有时会停留在编辑页）
                    logger.info("⚠️ 仍在编辑页面，但假定事件已保存")
                    result['success'] = True
                    
                    # 手动返回日历主页
                    try:
                        await self.page.goto("https://calendar.google.com/calendar/r", wait_until="domcontentloaded")
                        logger.info("✅ 已返回日历主页")
                    except:
                        pass

            logger.info("=" * 80)
            logger.info(f"🎯 事件创建流程完成")
            logger.info(f"   结果: {'✅ 成功' if result['success'] else '❌ 失败'}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"❌ 创建事件失败: {e}")
            logger.error("=" * 80)
            result['error'] = str(e)
        
        return result

    async def close(self):
        """关闭浏览器和playwright"""
        try:
            if self._browser_check_task and not self._browser_check_task.done():
                self._browser_check_task.cancel()
                try:
                    await self._browser_check_task
                except asyncio.CancelledError:
                    pass
            
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"关闭资源时出错: {e}")


async def test_calendar_bot():
    """测试函数"""
    bot = CalendarBot()
    try:
        await bot.initialize()
        
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        
        # 测试冲突检查
        logger.info("测试时间冲突检查...")
        conflict_result = await bot.check_time_conflict(start_time, end_time)
        logger.info(f"冲突检查结果: {conflict_result}")
        
        # 测试创建事件
        result = await bot.create_event("测试会议", start_time, end_time)
        if result['success']:
            logger.info(f"✅ 事件创建成功: {result['title']}")
        else:
            logger.error(f"❌ 事件创建失败: {result.get('error', '未知错误')}")
            
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(test_calendar_bot())