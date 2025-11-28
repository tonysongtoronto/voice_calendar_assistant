import re
import logging
from datetime import datetime, timedelta, time

logger = logging.getLogger(__name__)

class NLPParser:

    # ---------------------
    # 兼容旧版接口
    # ---------------------
    def parse_event(self, text: str):
        """保持与 app.py 兼容"""
        return self.parse(text)

    # ---------------------
    # 主入口
    # ---------------------
    def parse(self, text: str):
        logger.info(f"解析文本: {text}")

        # 繁体转简体 + 常见字符替换
        text = self._normalize_text(text)
        logger.info(f"纠错后的文本: {text}")

        # 日期
        date = self.extract_date(text)
        if date is None:
            logger.warning("未能识别日期")
            return None

        # 时间
        time_pair = self.extract_time(text)
        if time_pair is None:
            logger.warning("未能识别时间，解析失败")
            return None

        start_time, end_time = time_pair
        # 如果 start_time == end_time，默认 1 小时
        if start_time == end_time:
            dt_start = datetime.combine(date, start_time)
            dt_end = dt_start + timedelta(hours=1)
            start_time = dt_start.time()
            end_time = dt_end.time()

        start_dt = datetime.combine(date, start_time)
        end_dt = datetime.combine(date, end_time)

        # 标题
        title = self.extract_title(text)

        return {
            "title": title,
            "start_time": start_dt,
            "end_time": end_dt
        }

    # ---------------------
    # 繁体字符转换 + 常见修正
    # ---------------------
    def _normalize_text(self, text: str):
        mapping = {
            "兩": "两",
            "會": "会",
            "幫": "帮",
            "點": "点",
            "回憶": "回忆",
            "今": "今",
            "明": "明",
            "後": "后",
            "钟": "钟",
            "鐘": "钟",
        }
        for k, v in mapping.items():
            text = text.replace(k, v)
        return text

    # ---------------------
    # 日期解析
    # ---------------------
    def extract_date(self, text: str):
        today = datetime.today()
        if "今天" in text:
            return today.date()
        if "明天" in text:
            return (today + timedelta(days=1)).date()
        if "后天" in text:
            return (today + timedelta(days=2)).date()
        return today.date()  # 默认今天

    # ---------------------
    # 时间解析（支持时间区间）
    # ---------------------
    def extract_time(self, text: str):
        # 匹配 "下午2点到3点" 或 "下午两点半到三点半"
        range_pattern = r"(早上|上午|中午|下午|晚上)?\s*([0-9零一二三四五六七八九十两百]+)\s*点(半|[0-9零一二三四五六七八九十两百]+分)?\s*(?:到|至)\s*([0-9零一二三四五六七八九十两百]+)\s*点(半|[0-9零一二三四五六七八九十两百]+分)?"
        m = re.search(range_pattern, text)
        if m:
            period = m.group(1)
            start_hour = self.chinese_to_number(m.group(2))
            start_minute = 30 if m.group(3)=="半" else (self.chinese_to_number(m.group(3).replace("分","")) if m.group(3) else 0)
            end_hour = self.chinese_to_number(m.group(4))
            end_minute = 30 if m.group(5)=="半" else (self.chinese_to_number(m.group(5).replace("分","")) if m.group(5) else 0)

            if period in ["下午","晚上"]:
                if start_hour < 12:
                    start_hour += 12
                if end_hour < 12:
                    end_hour += 12
            if period=="中午":
                if start_hour <12:
                    start_hour +=12
                if end_hour <12:
                    end_hour +=12

            return (time(start_hour,start_minute), time(end_hour,end_minute))

        # 单点时间匹配
        single_pattern = r"(早上|上午|中午|下午|晚上)?\s*([0-9零一二三四五六七八九十两百]+)\s*点(半|[0-9零一二三四五六七八九十两百]+分)?"
        m = re.search(single_pattern, text)
        if m:
            period = m.group(1)
            hour = self.chinese_to_number(m.group(2))
            minute = 30 if m.group(3)=="半" else (self.chinese_to_number(m.group(3).replace("分","")) if m.group(3) else 0)

            if period in ["下午","晚上"]:
                if hour < 12:
                    hour += 12
            if period=="中午" and hour <12:
                hour +=12

            return (time(hour,minute), time(hour,minute))  # 上层处理 +1 小时

        return None

    # ---------------------
    # 标题解析
    # ---------------------
    def extract_title(self, text: str):
        if "会议" in text or "开会" in text:
            return "会议"
        if "提醒" in text:
            return "提醒"
        if "安排" in text or "回忆" in text:
            return "安排事项"
        return "日程"

    # ---------------------
    # 中文数字转阿拉伯数字
    # ---------------------
    def chinese_to_number(self, cn: str):
        table = {
            "零":0,"一":1,"二":2,"两":2,"三":3,"四":4,
            "五":5,"六":6,"七":7,"八":8,"九":9,"十":10
        }

        if cn.isdigit():
            return int(cn)

        if cn=="十":
            return 10

        if cn.startswith("十"): # 十一
            return 10 + table[cn[1:]]
        if cn.endswith("十"): # 三十
            return table[cn[0]]*10
        if "十" in cn: # 二十三
            parts = cn.split("十")
            return table[parts[0]]*10 + table[parts[1]]

        return table.get(cn,0)
