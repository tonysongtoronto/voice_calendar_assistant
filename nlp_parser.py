import re
import logging
from datetime import datetime, timedelta, time
import calendar

logger = logging.getLogger(__name__)

class NLPParser:
    def __init__(self):
        # 同音词纠错映射
        self.error_correction_map = {
            "回忆": "会议",
            "会意": "会议",
            "会义": "会议",
            "huiyi": "会议",
        }
        
        # 月份名称映射
        self.month_map = {
            "一月": 1, "二月": 2, "三月": 3, "四月": 4, "五月": 5,
            "六月": 6, "七月": 7, "八月": 8, "九月": 9, "十月": 10,
            "十一月": 11, "十二月": 12,
            "正月": 1, "腊月": 12,
            "1月": 1, "2月": 2, "3月": 3, "4月": 4, "5月": 5,
            "6月": 6, "7月": 7, "8月": 8, "9月": 9, "10月": 10,
            "11月": 11, "12月": 12,
        }
        
        # 星期映射
        self.weekday_map = {
            "一": 0, "1": 0,
            "二": 1, "2": 1,
            "三": 2, "3": 2,
            "四": 3, "4": 3,
            "五": 4, "5": 4,
            "六": 5, "6": 5,
            "日": 6, "天": 6, "7": 6, "0": 6
        }
        
        # 基础数字映射
        self.chinese_numbers = {
            "零": 0, "一": 1, "壹": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "拾": 10
        }

    def parse_event(self, text: str):
        """兼容旧接口"""
        return self.parse(text)

    def parse(self, text: str):
        """主解析入口"""
        logger.info(f"📥 原始输入: {text}")
        
        # 多阶段文本处理
        text = self._normalize_text(text)
        logger.info(f"✏️ 基础纠错后: {text}")
        
        text = self._apply_error_correction(text)
        logger.info(f"🔧 同音词纠错后: {text}")
        
        text = self._normalize_chinese_numbers_in_date(text)
        logger.info(f"🔢 数字标准化后: {text}")
        
        text = self._preprocess_date_patterns(text)
        logger.info(f"📅 日期预处理: {text}")
        
        # 解析日期
        date = self.extract_date(text)
        if date is None:
            logger.warning("⚠️ 未能识别日期,使用今天")
            date = datetime.today().date()
        
        # 解析时间
        time_pair = self.extract_time(text)
        if time_pair is None:
            logger.warning("❌ 未能识别时间")
            return {
                "success": False,
                "error": "抱歉,我没有听清楚时间。请说具体几点,比如下午2点。"
            }
        
        start_time, end_time = time_pair
        if start_time == end_time:  # 默认1小时
            dt_start = datetime.combine(date, start_time)
            dt_end = dt_start + timedelta(hours=1)
            start_time = dt_start.time()
            end_time = dt_end.time()
        
        start_dt = datetime.combine(date, start_time)
        end_dt = datetime.combine(date, end_time)
        
        # 解析标题
        title = self.extract_title(text)
        
        result = {
            "title": title,
            "start_time": start_dt,
            "end_time": end_dt,
            "success": True
        }
        
        logger.info(f"✅ 最终解析结果: {result}")
        return result

    def _normalize_text(self, text: str):
        """繁体转简体"""
        mapping = {
            "兩": "两", "會": "会", "幫": "帮", "點": "点",
            "今": "今", "明": "明", "後": "后",
            "钟": "钟", "鐘": "钟", "號": "号", "週": "周",
        }
        for k, v in mapping.items():
            text = text.replace(k, v)
        return text

    def _apply_error_correction(self, text: str):
        """同音词纠错"""
        for wrong, correct in self.error_correction_map.items():
            text = text.replace(wrong, correct)
        
        # 处理"428回忆" → "4月28日会议"
        def replace_compact_date(match):
            num = match.group(1)
            if len(num) == 3 and num[0] in "123456789":
                month, day = num[0], num[1:]
            elif len(num) == 4:
                month, day = (num[1:2], num[2:]) if num.startswith("0") else (num[:2], num[2:])
            else:
                return match.group(0)
            
            try:
                m, d = int(month), int(day)
                if 1 <= m <= 12 and 1 <= d <= 31:
                    return f"{m}月{d}日"
            except:
                pass
            return match.group(0)
        
        text = re.sub(r"(\d{3,4})\s*(会议|回忆|会|议)", replace_compact_date, text)
        return text

    def _normalize_chinese_numbers_in_date(self, text: str):
        """中文数字日期转阿拉伯数字"""
        # 处理"二十号"、"二十一日"
        pattern = r"(二十[一二三四五六七八九]?|三十[一]?|[零一二三四五六七八九十壹拾]+)\s*(号|日)"
        def replace_date_number(match):
            cn_num = match.group(1)
            number = self.chinese_to_number(cn_num)
            return f"{number}日" if number > 0 else match.group(0)
        text = re.sub(pattern, replace_date_number, text)
        
        # 处理月份
        month_pattern = r"(十一|十二|[零一二三四五六七八九十壹拾]+)月"
        def replace_month_number(match):
            cn_month = match.group(1)
            month = self.chinese_to_number(cn_month)
            return f"{month}月" if 1 <= month <= 12 else match.group(0)
        text = re.sub(month_pattern, replace_month_number, text)
        
        return text

    def _preprocess_date_patterns(self, text: str):
        """预处理特殊日期格式"""
        text = text.replace(" ", "")
        
        # 处理中文月份:"十一月二十八日"
        chinese_month_pattern = r"(正月|一月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月)([0-9零一二两三四五六七八九十壹拾]+)[日号]"
        match = re.search(chinese_month_pattern, text)
        if match:
            month_name = match.group(1)
            day_str = match.group(2)
            
            month = self.month_map.get(month_name)
            day = self.chinese_to_number(day_str)
            
            if month and day and 1 <= day <= 31:
                text = re.sub(chinese_month_pattern, f"{month}月{day}日", text)
                logger.info(f"🔄 转换中文日期: {month_name}{day_str}日 → {month}月{day}日")
        
        # 处理点格式:"11.28" → "11月28日"
        dotted_pattern = r"(1[0-2]|0?[1-9])[·\.]([0-9]{1,2})"
        match = re.search(dotted_pattern, text)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            if 1 <= day <= 31:
                text = re.sub(dotted_pattern, f"{month}月{day}日", text)
                logger.info(f"🔄 转换点格式日期: {match.group(0)} → {month}月{day}日")
        
        return text

    def extract_date(self, text: str):
        """提取日期"""
        today = datetime.today()
        text = text.replace(" ", "")
        
        # 尝试多种解析器 - 调整优先级
        parsers = [
            self._parse_base_keywords,        # 最高优先级:今天、明天、后天
            self._parse_specific_date,        # 具体日期:12月25日
            self._parse_relative_weekday,     # 相对星期:下周二、本周五
            self._parse_week_month_date,      # 下周、下月
            self._parse_day_relative_date,    # N天后
        ]
        
        for parser in parsers:
            date = parser(text, today)
            if date:
                logger.info(f"✅ {parser.__name__} 成功: {date}")
                return date
        
        logger.warning("⚠️ 所有解析器失败,返回今天")
        return today.date()

    def _parse_base_keywords(self, text: str, today: datetime):
        """解析基础关键词:今天、明天、后天 - 提升到最高优先级"""
        if "今天" in text or "今日" in text:
            return today.date()
        
        if "明天" in text or "明日" in text:
            return (today + timedelta(days=1)).date()
        
        if "后天" in text:
            return (today + timedelta(days=2)).date()
        
        if "大后天" in text:
            return (today + timedelta(days=3)).date()
        
        if "昨天" in text or "昨日" in text:
            return (today - timedelta(days=1)).date()
        
        if "前天" in text:
            return (today - timedelta(days=2)).date()
        
        return None

    def _parse_specific_date(self, text: str, today: datetime):
        """解析具体日期:12月25日、12/25、以及仅日期如11日"""
        patterns = [
            r"(1[0-2]|0?[1-9])月(\d{1,2})[日号]?",
            r"(1[0-2]|0?[1-9])[/\-\.]([0-9]{1,2})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                
                year = today.year
                # 如果指定的日期已经过去,则认为是明年
                if today.month > month or (today.month == month and today.day > day):
                    year += 1
                
                try:
                    return datetime(year, month, day).date()
                except ValueError:
                    logger.warning(f"❌ 无效日期: {year}-{month}-{day}")
                    continue
        
        # 如果没有月份，仅有日期，假设本月，若已过则下月
        day_only_pattern = r"(\d{1,2})[日号]?"
        match = re.search(day_only_pattern, text)
        if match:
            day = int(match.group(1))
            year = today.year
            month = today.month
            if day < today.day:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            try:
                return datetime(year, month, day).date()
            except ValueError:
                logger.warning(f"❌ 无效日期: {year}-{month}-{day}")
                return None
        
        return None

    def _parse_relative_weekday(self, text: str, today: datetime):
        """解析相对星期:下周二、本周五 - 修复版"""
        # 匹配格式:下周二、本周五、下下周三、周五
        pattern = r"(下下|下|本|这|上)?\s*个?\s*(周|星期)([一二三四五六日天])"
        match = re.search(pattern, text)
        
        if not match:
            return None
        
        prefix = match.group(1) or ""
        weekday_cn = match.group(3)
        
        target_weekday = self.weekday_map.get(weekday_cn)
        if target_weekday is None:
            return None
        
        current_weekday = today.weekday()
        logger.info(f"🔍 相对星期解析: prefix='{prefix}', weekday={weekday_cn}({target_weekday}), today_weekday={current_weekday}")
        
        if prefix == "下":
            # "下周X" = 从下周一开始算第X天
            days_until_next_monday = (7 - current_weekday) % 7
            if days_until_next_monday == 0:  # 今天是周一
                days_until_next_monday = 7
            days_ahead = days_until_next_monday + target_weekday
            
        elif prefix == "下下":
            # "下下周X" = 从下下周一开始算第X天
            days_until_next_monday = (7 - current_weekday) % 7
            if days_until_next_monday == 0:
                days_until_next_monday = 7
            days_ahead = days_until_next_monday + 7 + target_weekday
            
        elif prefix in ["本", "这"]:
            # "本周X" = 从本周一开始算第X天
            # 如果目标日期已过,则指向下周的该天
            days_since_monday = current_weekday
            days_ahead = target_weekday - days_since_monday
            if days_ahead <= 0:  # 如果是今天或已经过去
                days_ahead += 7  # 指向下周
                
        elif prefix == "上":
            # "上周X" = 上周的第X天
            days_since_monday = current_weekday
            days_ahead = target_weekday - days_since_monday - 7
            
        else:
            # 无前缀,如"周五" - 指最近的未来星期五
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:  # 今天就是目标星期几
                days_ahead = 7  # 指向下周
        
        target_date = today + timedelta(days=days_ahead)
        logger.info(f"✅ 计算结果: days_ahead={days_ahead}, target={target_date.date()}")
        return target_date.date()

    def _parse_week_month_date(self, text: str, today: datetime):
        """解析周/月相对日期:下周、下月、下下下个月15号"""
        text = text.replace(" ", "")
        
        # 检测"下周"(不含星期几)
        if re.search(r"下+\s*周(?![一二三四五六日天])", text):
            weeks_match = re.search(r"(下+)\s*周", text)
            if weeks_match:
                weeks_ahead = weeks_match.group(1).count("下")
                # 计算到下N周一的天数
                days_until_next_monday = (7 - today.weekday()) % 7
                if days_until_next_monday == 0:
                    days_until_next_monday = 7
                days_ahead = days_until_next_monday + (weeks_ahead - 1) * 7
                target_date = today + timedelta(days=days_ahead)
                logger.info(f"✅ 下周解析: weeks={weeks_ahead}, target={target_date.date()}")
                return target_date.date()
        
        # 检测"下月"或"下个月"
        month_pattern = r"(下+)\s*个?\s*月(?:\s*(\d{1,2})[日号])?"
        match = re.search(month_pattern, text)
        
        if match:
            prefix = match.group(1)
            day_num = match.group(2)
            
            months_ahead = prefix.count("下")
            target_year = today.year
            target_month = today.month + months_ahead
            
            while target_month > 12:
                target_month -= 12
                target_year += 1
            
            if day_num:
                day = int(day_num)
                try:
                    return datetime(target_year, target_month, day).date()
                except ValueError:
                    last_day = calendar.monthrange(target_year, target_month)[1]
                    return datetime(target_year, target_month, last_day).date()
            else:
                # 如果没指定日期,返回该月1号
                return datetime(target_year, target_month, 1).date()
        
        return None

    def _parse_day_relative_date(self, text: str, today: datetime):
        """解析天数相对日期:一天后、三天后、一周后"""
        text = text.replace(" ", "")
        
        patterns = [
            (r"(\d+|[零一二两三四五六七八九十壹拾]+)\s*天\s*后?", "days"),
            (r"(\d+|[零一二两三四五六七八九十壹拾]+)\s*周\s*后?", "weeks"),
            (r"(\d+|[零一二两三四五六七八九十壹拾]+)\s*个?\s*月\s*后?", "months"),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, text)
            if match:
                number_str = match.group(1)
                number = self.chinese_to_number(number_str)
                
                if number is None or number == 0:
                    continue
                
                if unit == "days":
                    return (today + timedelta(days=number)).date()
                elif unit == "weeks":
                    return (today + timedelta(weeks=number)).date()
                elif unit == "months":
                    year = today.year + (today.month + number - 1) // 12
                    month = (today.month + number - 1) % 12 + 1
                    
                    last_day = calendar.monthrange(year, month)[1]
                    day = min(today.day, last_day)
                    
                    return datetime(year, month, day).date()
        
        return None

    def extract_time(self, text: str):
        """提取时间"""
        # 时间段格式
        range_patterns = [
            r"(早上|上午|中午|下午|晚上)?\s*([0-9零一二两三四五六七八九十]+)\s*点(半|[0-9零一二两三四五六七八九十]+分)?\s*(?:到|至|-|~)\s*([0-9零一二两三四五六七八九十]+)\s*点(半|[0-9零一二两三四五六七八九十]+分)?",
            r"([0-9]{1,2}):([0-9]{2})\s*(?:到|至|-|~)\s*([0-9]{1,2}):([0-9]{2})",
            r"([0-9]{1,2}):([0-9]{2})\s*(?:到|至|-|~)\s*([0-9]{1,2})\s*点?",
        ]
        
        for pattern in range_patterns:
            m = re.search(pattern, text)
            if m:
                if pattern == range_patterns[0]:  # 中文格式
                    period = m.group(1)
                    start_hour = self.chinese_to_number(m.group(2))
                    start_minute = 30 if m.group(3) == "半" else (self.chinese_to_number(m.group(3).replace("分","")) if m.group(3) else 0)
                    end_hour = self.chinese_to_number(m.group(4))
                    end_minute = 30 if m.group(5) == "半" else (self.chinese_to_number(m.group(5).replace("分","")) if m.group(5) else 0)
                else:  # 数字格式
                    start_hour = int(m.group(1))
                    start_minute = int(m.group(2))
                    end_hour = int(m.group(3))
                    end_minute = int(m.group(4))
                    period = None
                
                # 处理上午/下午
                if period in ["下午","晚上"]:
                    if start_hour < 12: start_hour += 12
                    if end_hour < 12: end_hour += 12
                elif period == "中午" and start_hour < 12:
                    start_hour += 12
                    end_hour += 12
                elif period in ["早上", "上午"] and start_hour == 12:
                    start_hour = 0
                    end_hour = 1
                
                return (time(start_hour,start_minute), time(end_hour,end_minute))
        
        # 单个时间
        single_patterns = [
            r"(早上|上午|中午|下午|晚上)?\s*([0-9零一二两三四五六七八九十]+)\s*点(半|[0-9零一二两三四五六七八九十]+分)?",
            r"([0-9]{1,2}):([0-9]{2})",
        ]
        
        for pattern in single_patterns:
            m = re.search(pattern, text)
            if m:
                if pattern == single_patterns[0]:
                    period = m.group(1)
                    hour = self.chinese_to_number(m.group(2))
                    minute = 30 if m.group(3) == "半" else (self.chinese_to_number(m.group(3).replace("分","")) if m.group(3) else 0)
                else:
                    hour = int(m.group(1))
                    minute = int(m.group(2))
                    period = None
                
                # 处理上午/下午
                if period in ["下午","晚上"]:
                    if hour < 12: hour += 12
                elif period == "中午" and hour < 12:
                    hour += 12
                elif period in ["早上", "上午"] and hour == 12:
                    hour = 0
                
                return (time(hour,minute), time(hour,minute))
        
        return None

    def extract_title(self, text: str):
        """提取标题"""
        text = re.sub(r"(早上|上午|中午|下午|晚上)?\s*[0-9零一二两三四五六七八九十]+点([0-9零一二两三四五六七八九十]+分|半)?", "", text)
        text = re.sub(r"[0-9]{1,2}:[0-9]{2}", "", text)
        text = re.sub(r"(今天|明天|后天|大后天|昨天|前天|上周|下周|本周|这周|下下|下|上|本|这|个|周|星期|月|号|日)", "", text)
        text = re.sub(r"(1[0-2]|0?[1-9])月(\d{1,2})[日号]?", "", text)
        text = text.replace("是", "").replace("在", "").replace("请安排", "").replace("到","").replace("至","").strip()
        
        if not text:
            return "日程安排"
        
        return text[:20] if len(text) > 20 else text

    def chinese_to_number(self, cn: str):
        """中文数字转整数 - 完整实现"""
        if not cn or not isinstance(cn, str):
            return 0
        
        if cn.isdigit():
            return int(cn)
        
        # 处理十的倍数
        if cn == "二十":
            return 20
        if cn == "三十":
            return 30
        if cn == "十":
            return 10
        
        # 处理21-29
        if cn.startswith("二十"):
            unit = cn[2:]
            unit_num = self.chinese_numbers.get(unit, 0)
            return 20 + unit_num
        
        # 处理31
        if cn == "三十一":
            return 31
        
        # 处理13-19, 包括壹
        if cn.startswith("十"):
            unit = cn[1:]
            unit_num = self.chinese_numbers.get(unit, 0)
            return 10 + unit_num
        
        # 单独的数字
        return self.chinese_numbers.get(cn, 0)


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    parser = NLPParser()
    
    # 重点测试用例
    test_cases = [
        # 基础相对日期 - 这是主要测试项
        "明天下午2点开会",
        "后天上午10点",
        "今天晚上7点",
        
        # 相对星期 - 重点修复项
        "下周二下午3点会议",
        "本周五下午2点",
        "下下周三上午10点",
        "周五下午4点",
        
        # 下周/下月 - 重点修复项
        "下周上午10点",
        "下个月15号下午3点",
        "下下个月10号",
        
        # 具体日期
        "12月25日晚上8点",
        "十一月二十八日下午2点",
        "11.30下午3点",
        
        # N天后
        "三天后下午2点",
        "一周后上午10点",
        
        # 复杂表达
        "请安排428回忆下午3点",
        "二十号下午三点开会",
        
        # 新增: 日/号 测试
        "十一号下午2点",
        "十一日晚上8点",
        
        # 新增: 月份发音混淆测试 (假设ASR误认)
        "十壹月1日下午3点",  # 应解析为11月1日 (next year)
        "拾月二十五日中午12点",  # 应解析为10月25日
    ]
    
    print("=" * 100)
    print(f"{'序号':<4} {'输入':<35} {'标题':<15} {'日期':<12} {'时间':<20}")
    print("-" * 100)
    
    for i, text in enumerate(test_cases, 1):
        result = parser.parse(text)
        if result and result.get('success', True):
            title = result['title'][:13] if len(result['title']) > 13 else result['title']
            date_str = result['start_time'].strftime('%Y-%m-%d')
            time_str = f"{result['start_time'].strftime('%H:%M')}-{result['end_time'].strftime('%H:%M')}"
            weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][result['start_time'].weekday()]
            print(f"{i:<4} {text:<35} {title:<15} {date_str}({weekday}) {time_str:<20}")
        else:
            error = result.get('error', '解析失败') if isinstance(result, dict) else '解析失败'
            print(f"{i:<4} {text:<35} ❌ {error}")
    
    print("\n" + "=" * 100)
    print("📝 测试说明:")
    print("- 今天是 2025-11-28 (周五)")
    print("- 明天 = 11-29 (周六)")
    print("- 后天 = 11-30 (周日)")
    print("- 下周二 = 12-02 (周二)")
    print("- 本周五 = 12-05 (周五,因为今天已经是周五,所以指下周五)")
    print("- 下周 = 12-01 (下周一)")
    print("- 十一号/十一日 = 2025-12-11 (本月11日已过,指下月11日)")
    print("- 十壹月1日 = 2026-11-01 (本年11月1日已过,指明年)")
    print("- 拾月25日 = 2025-10-25 (但10月已过? 按代码逻辑: month=10 <11, so next year 2026-10-25)")
    print("=" * 100)