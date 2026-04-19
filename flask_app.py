#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
班级成长管家 - PythonAnywhere部署版 v3
核心升级：完整语义解析引擎（从本地版移植）
数据存储在本地JSON文件
"""
from flask import Flask, request, jsonify, send_from_directory, Response
import json
import os
import re
import time
import urllib.request
import ssl
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='public')

# ===== 配置 =====
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

# 四大维度
DIMENSIONS = ["学术发展", "个人成长", "社会性发展", "特色与潜能"]

# ===== 腾讯文档智能表格配置 =====
TDOC_TOKEN = "68f6acecb5ce46bf8d22062b77a1cc78"
TDOC_API = "https://docs.qq.com/openapi/mcp"
TDOC_FILE_ID = "KZYeTgkjnrpT"
TDOC_SHEET_ID = "t00i2h"
TDOC_URL = "https://docs.qq.com/smartsheet/DS1pZZVRna2pucnBU"

# SSL上下文（用于腾讯文档API调用）
_ssl_ctx = ssl.create_default_context()

def tdoc_call(tool_name, args_dict):
    """调用腾讯文档MCP API"""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args_dict},
        "id": 1
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        TDOC_API, data=data,
        headers={"Authorization": TDOC_TOKEN, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx)
        result = json.loads(resp.read().decode("utf-8"))
        # 检查JSON-RPC层级的错误
        if "error" in result:
            err = result["error"]
            if isinstance(err, dict):
                return {"error": err.get("message", str(err))}
            else:
                return {"error": str(err)}
        if "result" in result:
            content = result["result"].get("content", [])
            for c in content:
                if c.get("type") == "text":
                    try:
                        parsed = json.loads(c["text"])
                        return parsed
                    except:
                        return {"text": c["text"]}
        return result
    except Exception as e:
        return {"error": str(e)}

def _text_val(s):
    """格式化文本字段值"""
    return [{"text": str(s), "type": "text"}]

def _option_val(s):
    """格式化单选字段值"""
    return [{"text": str(s)}]

def _date_val(date_str):
    """将日期字符串转为毫秒时间戳字符串（腾讯文档日期字段要求）"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        ts = int(dt.timestamp() * 1000)
        return str(ts)
    except:
        return ""

def tdoc_add_records(records):
    """同步记录到腾讯文档智能表格（严格按字段类型格式化）"""
    formatted = []
    for r in records:
        formatted.append({
            "field_values": {
                "学生姓名": _text_val(r["student"]),
                "date": _date_val(r["date"]),
                "记录维度": _option_val(r["dimension"]),
                "归纳描述": _text_val(r.get("summary", "")),
                "原始描述": _text_val(r.get("description", "")),
                "记录人": _text_val(r.get("recorder", "梁老师"))
            }
        })
    # 逐条添加（比批量更可靠，避免单条失败导致整批丢失）
    results = []
    for record in formatted:
        r = tdoc_call("smartsheet.add_records", {
            "file_id": TDOC_FILE_ID,
            "sheet_id": TDOC_SHEET_ID,
            "records": [record]
        })
        results.append(r)
    return results

def tdoc_list_records():
    """从腾讯文档获取所有记录"""
    return tdoc_call("smartsheet.list_records", {
        "file_id": TDOC_FILE_ID,
        "sheet_id": TDOC_SHEET_ID,
        "offset": 0,
        "limit": 100
    })

# ===== 语义解析引擎（从本地版server.py完整移植） =====
# 基于评分的多维度分类，比简单关键词匹配精确得多

DIMENSION_RULES = {
    "学术发展": {
        "primary": ["课堂", "作业", "成绩", "考试", "测验", "数学", "英语", "语文", "科学",
                    "阅读", "写作", "背诵", "预习", "复习", "笔记", "提问", "回答", "发言",
                    "项目", "思维", "学习", "知识", "题", "实验", "分析", "解题", "研究",
                    "探究", "方案", "展示", "思路", "逻辑", "理解", "掌握"],
        "secondary": ["态度端正", "勤能补拙", "认真", "努力学"],
        "negative": []
    },
    "个人成长": {
        "primary": ["习惯", "品格", "品质", "心态", "态度", "情绪", "自律", "坚持", "诚实",
                    "守时", "准时", "细心", "耐心", "勇气", "勤奋", "自信", "反思", "改正",
                    "成长", "进步", "改变", "坚强", "乐观", "积极", "自我管理", "规划",
                    "计划", "目标", "紧张", "焦虑", "心态不好", "容易紧张", "笑嘻嘻",
                    "可爱", "正气", "一身正气", "勤能补拙", "胖乎乎",
                    "自己要", "自驱", "内驱", "自觉", "自我", "主动"],
        "secondary": [],
        "negative": ["班长", "为班级", "做事最多", "志愿者"]
    },
    "社会性发展": {
        "primary": ["合作", "协作", "团队", "小组", "沟通", "交流", "帮助", "责任", "班级",
                    "值日", "扫地", "擦", "劳动", "班长", "班委", "干部", "服务",
                    "规则", "纪律", "秩序", "礼貌", "尊重", "友善", "关心", "同学",
                    "朋友", "集体", "组织", "协调", "解决冲突", "义务", "负责",
                    "为班级", "为年级", "做事", "付出", "志愿者", "家访", "哭",
                    "调皮", "捣蛋", "对着干", "顶撞", "听话", "关系", "师生",
                    "缓和", "改善", "叛逆", "对抗", "抵触", "顺从", "配合",
                    "对抗", "不听话", "管教", "违反", "捣乱", "闹腾"],
        "secondary": [],
        "negative": ["最喜欢", "一身正气", "可爱"]
    },
    "特色与潜能": {
        "primary": ["特长", "创意", "创新", "领导", "领导力", "才艺", "绘画", "音乐", "体育",
                    "运动", "竞赛", "比赛", "获奖", "奖项", "编程", "设计", "发明",
                    "游戏", "表演", "主持", "策划", "独特", "擅长", "兴趣", "爱好",
                    "潜力", "突出", "优秀", "贡献", "亮点", "最喜欢", "做事最多",
                    "一身正气", "默默付出", "不可替代"],
        "secondary": [],
        "negative": []
    }
}


def score_text_for_dimension(text, dim_name):
    """为文本在某个维度上打分"""
    rules = DIMENSION_RULES.get(dim_name, {})
    score = 0
    for kw in rules.get("primary", []):
        count = text.count(kw)
        if count > 0:
            score += 2 * count
    for kw in rules.get("secondary", []):
        if kw in text:
            score += 1
    for kw in rules.get("negative", []):
        if kw in text:
            score -= 3
    return score


def classify_dimension(text):
    """将文本归类到最匹配的维度（基于评分）"""
    scores = {}
    for dim in DIMENSION_RULES:
        scores[dim] = score_text_for_dimension(text, dim)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "个人成长"  # 默认
    return best


def split_into_segments(text):
    """将长段话按语义切分为多个片段（支持逗号级别的细粒度切分）"""
    # 第一层：按句号、感叹号等大标点切分
    big_segments = re.split(r'[。！？；\n]', text)
    
    # 对每个大段进一步按逗号切分为小句
    all_clauses = []
    for seg in big_segments:
        seg = seg.strip()
        if not seg:
            continue
        # 按逗号切分
        clauses = re.split(r'[，,]', seg)
        for c in clauses:
            c = c.strip()
            if c and len(c) >= 2:
                all_clauses.append(c)
    
    if not all_clauses:
        return [text]
    
    # 将小句按维度合并：相邻且同维度的合并为一段
    segments = []
    current = ""
    current_dim = None
    
    for clause in all_clauses:
        clause_dim = classify_dimension(clause)
        
        if current:
            # 太短的从句（感叹、总结等）合并到前一段，不单独拆分
            if len(clause) <= 8:
                current = current + "，" + clause
            # 如果维度相同，合并
            elif clause_dim == current_dim:
                current = current + "，" + clause
            else:
                # 维度不同，保存当前段，开始新段
                segments.append(current.strip())
                current = clause
                current_dim = clause_dim
        else:
            current = clause
            current_dim = clause_dim
    
    if current.strip():
        segments.append(current.strip())
    
    # 过滤太短的段
    segments = [s for s in segments if len(s) >= 4]
    
    return segments if segments else [text]


def extract_date_from_text(text):
    """从文本提取日期"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 完整日期
    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', text)
    if date_match:
        return f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    # 月日
    month_match = re.search(r'(\d{1,2})月(\d{1,2})日?', text)
    if month_match:
        year = datetime.now().year
        return f"{year}-{int(month_match.group(1)):02d}-{int(month_match.group(2)):02d}"

    # 相对日期
    if "今天" in text or "今日" in text:
        return today
    elif "昨天" in text or "昨日" in text:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "前天" in text:
        return (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    return today


def clean_oral_text(text):
    """深度口语净化"""
    result = text
    filler_words = ["其实", "就是说", "然后", "那个", "就是", "反正", "怎么说呢",
                   "你知道吗", "对吧", "嘛", "吧", "啊", "呢", "哎", "哎呦", "嗯"]
    for fw in filler_words:
        result = result.replace(fw, "")
    result = re.sub(r"比如说\s*", "", result)
    result = re.sub(r"真的很(.{1,2})很\1", r"真的很\1", result)
    result = re.sub(r'\s+', '', result)
    return result.strip()


def integrate_academic(observations):
    """整合学术发展观察：找出核心学习画像"""
    has_diligence = any("勤奋" in o or "端正" in o or "投入" in o for o in observations)
    has_weakness = any("待夯实" in o or "不足" in o or "分散" in o for o in observations)
    has_strength = any("良好" in o or "优势" in o or "积极" in o for o in observations)
    has_top_rank = any("前列" in o or "拔尖" in o or "优异" in o for o in observations)
    has_stable = any("稳定" in o for o in observations)
    has_allround = any("全面" in o for o in observations)
    has_honor = any("荣誉" in o for o in observations)
    has_talent = any("才艺" in o or "特长" in o for o in observations)

    if has_top_rank and has_allround and has_talent:
        return "学业成绩拔尖，各学科全面发展，且具有才艺特长，是全面发展的优秀学生"
    if has_top_rank and has_allround:
        return "学业成绩拔尖，各学科全面发展"
    if has_top_rank and has_stable:
        return "学业成绩优秀且稳定，始终处于班级前列"
    if has_top_rank:
        return "学业成绩优秀，在班级中名列前茅"
    if has_diligence and has_weakness:
        return "学习态度端正勤奋，学业基础尚在提升中，以坚持弥补差距"
    if has_diligence and has_strength:
        return "学习态度认真且学业表现良好，是稳步向上的学生"
    if has_weakness:
        return "学业基础有待加强，需要更多关注和引导"
    if has_strength and has_stable:
        return "学业表现良好且稳定"
    if has_strength:
        return "学业表现良好，学习状态积极"
    return "；".join(observations)


def integrate_personal(observations):
    """整合个人成长观察：描绘性格画像"""
    has_tension = any("紧张" in o or "情绪调节" in o or "敏感" in o for o in observations)
    has_positive = any("开朗" in o or "乐观" in o or "韧性" in o or "讨喜" in o or "良好" in o or "不错" in o for o in observations)
    has_righteous = any("正直" in o or "端正" in o for o in observations)
    has_self_discipline = any("自律" in o or "作息" in o or "习惯" in o for o in observations)
    has_family_support = any("家庭" in o or "支持系统" in o for o in observations)
    has_appearance = any("外表" in o or "戴眼镜" in o or "憨厚" in o or "亲和" in o for o in observations)
    has_puberty = any("青春期" in o or "变声期" in o for o in observations)

    if has_self_discipline and has_family_support:
        base = "生活习惯良好、自律性强，家庭环境温暖有支持"
        if has_positive:
            return base + "，整体发展健康阳光"
        return base + "，良好的家庭氛围为成长提供了稳定支撑"

    if has_tension and has_positive:
        return "表面开朗乐观，但在压力情境下容易紧张，内心需要更多安全感"
    if has_tension and has_righteous:
        return "品性正直，但在高压场合容易紧张，需要在安全环境中逐步建立自信"
    if has_positive and has_righteous:
        return "品性端正、性格开朗，是积极阳光的孩子"
    if has_tension:
        return "在压力和社交场合容易紧张，需要帮助建立心理韧性"

    if has_appearance and has_puberty:
        return "正处于青春期发育阶段，身心正在经历变化"

    if has_positive and has_self_discipline:
        return "生活自律，整体发展状态良好"

    if has_self_discipline:
        return "生活自律性好，习惯健康"

    return "；".join(observations)


def integrate_social(observations):
    """整合社会性发展观察：描绘社交与责任画像"""
    has_responsibility = any("责任" in o or "管理" in o or "付出" in o or "使命感" in o for o in observations)
    has_expression_issue = any("不善" in o or "忽视" in o or "表达" in o for o in observations)
    has_helping = any("助人" in o or "劳动" in o or "公益" in o or "志愿" in o or "帮老师" in o or "积极" in o for o in observations)
    has_competitiveness = any("好胜" in o or "竞争" in o or "争辩" in o or "落选" in o or "赌气" in o for o in observations)
    has_unreliable = any("不靠谱" in o or "不够细致" in o or "不够靠谱" in o or "过于活泼" in o or "执行力" in o for o in observations)
    has_active = any("活泼" in o or "积极" in o or "开朗" in o or "调皮" in o for o in observations)
    has_core = any("核心" in o or "领头" in o or "骨干" in o for o in observations)
    has_relationship_improve = any("改善" in o or "缓和" in o or "减少" in o or "配合" in o or "守规矩" in o or "向好" in o for o in observations)
    has_rebellion_past = any("对抗" in o or "曾有" in o for o in observations)

    # 师生关系改善画像
    if has_relationship_improve and has_rebellion_past:
        if has_active:
            return "性格调皮但师生关系明显改善，对抗行为减少，变得更加配合——转变积极向好"
        return "曾有对抗行为但正在改善，师生关系明显缓和，态度转变积极"

    if has_relationship_improve and has_active:
        return "性格活泼调皮，但人际关系在改善，整体发展态势向好"

    if has_relationship_improve:
        return "人际关系明显改善，变得更加配合守规矩"

    if has_rebellion_past:
        return "曾有对抗行为，需要持续关注师生关系的改善"

    if has_active and has_unreliable:
        if has_core:
            return "是班级核心学生之一，性格活泼、做事积极，但过于活泼导致执行力不够可靠——热心有余，细致不足"
        if has_helping:
            return "乐于参与班级事务、性格活泼，但做事不够细致可靠——热情有余，落地不足"
        return "性格活泼、做事积极主动，但过于活泼导致不够靠谱，需要培养做事的细致度"

    if has_core and has_unreliable:
        return "在班级中有核心影响力，但做事不够可靠，需要在热情与执行之间找到平衡"

    if has_competitiveness and has_responsibility:
        return "好胜心强、有责任心，但在竞争受挫时情绪反应强烈"
    if has_responsibility and has_expression_issue:
        return "责任心强、默默付出，但不善于展示自我，付出容易被忽视"
    if has_responsibility and has_helping:
        return "热心集体事务，责任心突出，是班级可靠的担当者"
    if has_competitiveness:
        return "好胜心强，对竞争结果敏感，需要学会面对挫折"
    if has_expression_issue:
        return "在表达自我方面存在困难，需要创造安全的表达空间"
    if has_responsibility:
        return "对集体有强烈的责任感和担当意识"
    if has_helping and has_active:
        return "乐于帮助他人、做事积极主动"
    return "；".join(observations)


def integrate_potential(observations):
    """整合特色与潜能观察：点出独特价值"""
    has_leadership = any("领导" in o or "组织" in o for o in observations)
    has_talent = any("才艺" in o or "创意" in o for o in observations)
    has_contribution = any("贡献" in o or "关注" in o for o in observations)

    if has_leadership and has_contribution:
        return "在集体中发挥着不可替代的作用，具有组织领导潜质"
    if has_talent:
        return "在特定领域有突出表现，值得进一步培养和引导"
    return "；".join(observations)


def summarize_text_rules(text, dimension):
    """增强版规则引擎：做语义整合而不是关键词拼接"""
    # 先做口语净化
    cleaned = clean_oral_text(text)

    # 维度专用的深度理解规则
    dim_understanding = {
        "学术发展": {
            "analyzers": [
                (r"成绩.{0,5}(不好|一般|差|不行)", lambda m: "学业基础尚待夯实"),
                (r"成绩(最好|第一|拔尖|顶尖)", lambda m: "学业成绩在班级拔尖"),
                (r"成绩.{0,5}(好|不错|优秀|突出)", lambda m: "学业表现良好"),
                (r"勤能补拙", lambda m: "勤奋踏实，以坚持弥补不足"),
                (r"态度.{0,4}(端正|认真|好)", lambda m: "学习态度端正自觉"),
                (r"态度.{0,4}(不好|差|敷衍)", lambda m: "学习态度有待端正"),
                (r"(数学|英语|语文|科学).{0,8}(好|优秀|突出|进步)", lambda m: f"{m.group(1)}学科优势明显"),
                (r"(语文|数学|英语|科学).{0,10}全面发展", lambda m: "各学科全面发展"),
                (r"课堂.{0,6}(积极|发言|提问|参与)", lambda m: "课堂参与积极主动"),
                (r"作业.{0,6}(全对|认真|完成.{0,2}好|完成得很|优秀)", lambda m: "作业完成质量高"),
                (r"作业.{0,6}(不交|拖拉|敷衍|没做|不完成|不认真)", lambda m: "作业习惯需关注"),
                (r"(努力|认真).{0,4}(学习|学|钻研)", lambda m: "学习投入度高"),
                (r"(分心|走神|开小差|不专注)", lambda m: "注意力容易分散"),
                (r"班级.{0,6}(第二|第三|前[二三]|前三)", lambda m: "学业成绩稳居班级前列"),
                (r"永远.{0,4}(第二|第三|前[二三])", lambda m: "学业成绩稳定在班级前列"),
                (r"成绩.{0,5}(稳定|没有波动)", lambda m: "学业成绩稳定"),
                (r"成绩.{0,5}(没掉|不掉|没降|不降|保持)", lambda m: "学业成绩稳定"),
                (r"非常非常.{0,3}(好|优秀)", lambda m: "学业表现优异"),
                (r"十佳|最高规格", lambda m: "获得过校级重要荣誉"),
                (r"乐器|打鼓|才艺", lambda m: "具有才艺特长"),
                # 自我驱动力（学术相关）
                (r"(自己|说明).{0,4}(要|想|会).{0,4}(读书|学习|努力)", lambda m: "具有学习自驱力"),
            ],
            "integrator": lambda observations: integrate_academic(observations)
        },
        "个人成长": {
            "analyzers": [
                (r"紧张|紧张", lambda m: "在压力情境下容易紧张"),
                (r"心态.{0,4}(不好|差|不稳|容易崩)", lambda m: "情绪调节能力尚在发展中"),
                (r"笑嘻嘻|整天笑|开朗|乐观", lambda m: "性格开朗乐观"),
                (r"正气|一身正气|正直", lambda m: "品性正直端正"),
                (r"可爱|讨人喜欢", lambda m: "性格温和讨喜"),
                (r"容易紧张|说不利索|人多.{0,4}紧张", lambda m: "社交场合容易紧张"),
                (r"心态好|抗压|坚强", lambda m: "心理韧性较好"),
                (r"(胖乎乎|胖胖|壮壮)", lambda m: "外形憨厚亲和"),
                (r"独立|自理", lambda m: "生活自理能力较强"),
                (r"敏感|细腻|心思重", lambda m: "内心细腻敏感"),
                (r"瘦瘦|瘦|黑|黑黑的", lambda m: "外表清瘦"),
                (r"戴.{0,3}眼镜", lambda m: "戴眼镜"),
                (r"变声期|声音.{0,4}(特点|特别|独特)", lambda m: "正处于青春期发育阶段"),
                (r"(没|不).{0,5}(上瘾|沉迷|手机|游戏|网)", lambda m: "生活自律，未沉迷电子产品"),
                (r"睡.{0,4}(早|规律|好)", lambda m: "作息规律健康"),
                (r"生活.{0,4}(习惯|规律|好)", lambda m: "生活习惯良好"),
                (r"家.{0,15}(和睦|温暖|支持|氛围好|关心)", lambda m: "家庭环境温暖有支持"),
                (r"家长|父母|家里面.{0,8}(好|支持|关心|和睦)", lambda m: "家庭支持系统良好"),
                (r"很好.{0,2}很好", lambda m: "整体发展良好"),
                (r"不错.{0,2}不错|真的不错", lambda m: "各方面表现良好"),
                # 自我驱动力
                (r"自己.{0,2}(要|想|会|能).{0,4}(读书|学习|做|努力)", lambda m: "具有自我驱动力"),
                (r"自驱|内驱|自觉|主动性", lambda m: "学习自觉性强"),
                (r"说明.{0,6}(要|想|会|能).{0,4}(读书|学习|努力)", lambda m: "内心有自我成长的动力"),
            ],
            "integrator": lambda observations: integrate_personal(observations)
        },
        "社会性发展": {
            "analyzers": [
                (r"班长|干部", lambda m: "承担班级管理职责"),
                (r"负责|责任心", lambda m: "责任心突出"),
                (r"为班级.{0,6}(做事|付出|做|操心)", lambda m: "主动为班级付出"),
                (r"值日|扫地|擦|劳动|打扫", lambda m: "积极参与班级劳动"),
                (r"志愿者|公益", lambda m: "热心公益志愿服务"),
                (r"哭.{0,10}(责任|班长|班级)", lambda m: "对集体有强烈的使命感"),
                (r"不善表达|说不利索|不会说", lambda m: "不善于表达自我"),
                (r"付出.{0,6}(不知道|看不到|没人知道)", lambda m: "付出常被忽视"),
                (r"帮助|帮忙|关心同学", lambda m: "乐于助人"),
                (r"家访", lambda m: "（家访了解）"),
                (r"好胜|要强|争强", lambda m: "好胜心强，对竞争结果敏感"),
                (r"赌气|不满|生气", lambda m: "遇到不公时情绪反应强烈"),
                (r"(没|不).{0,5}(选|投票|推荐)", lambda m: "对落选结果难以释怀"),
                (r"大队委员|班委|干部|代表", lambda m: "关注班级管理角色"),
                (r"争辩|反驳|顶嘴|不服", lambda m: "遇到不同意见时容易争辩"),
                (r"帮老师.{0,6}(做事|做事情|帮忙)", lambda m: "乐于帮助老师处理事务"),
                # 师生关系相关
                (r"和老师.{0,6}(关系.{0,4}(缓和|改善|好|不错)|相处.{0,4}(好|融洽|改善))", lambda m: "师生关系明显改善"),
                (r"老师.{0,6}(关系.{0,4}(缓和|改善|好)|相处.{0,4}(好|融洽))", lambda m: "师生关系明显改善"),
                (r"关系.{0,4}(缓和|改善|好|不错|融洽)", lambda m: "人际关系有所改善"),
                (r"(不对着干|不顶撞|不抵触|不再.{0,4}(对着干|顶撞|对抗))", lambda m: "对抗行为明显减少"),
                (r"(原来|之前|以前).{0,6}(对着干|顶撞|抵触|对抗|不听)", lambda m: "曾有对抗行为但正在改善"),
                (r"听话|守规矩|配合|顺从", lambda m: "变得更加配合守规矩"),
                (r"调皮|捣蛋|捣乱|闹腾", lambda m: "性格调皮活泼"),
                (r"再好不过|最好|最好不过|越来越好", lambda m: "整体发展态势向好"),
                # 活泼但不靠谱
                (r"活泼.{0,8}(不靠谱|不认真|不仔细|马虎)", lambda m: "性格活泼但做事不够细致"),
                (r"(不|没那么).{0,4}靠谱", lambda m: "做事不够靠谱稳重"),
                (r"很.{0,2}(活泼|开朗|积极).{0,8}(但|不过|但是|就是)", lambda m: "性格活泼但执行力有落差"),
                (r"太.{0,2}(活泼|开朗|积极)", lambda m: "性格过于活泼"),
                # 领头/核心
                (r"领头|核心|骨干|主力|带头人", lambda m: "在班级中具有核心影响力"),
                (r"三个人.{0,6}(领头|核心|主力|代表)", lambda m: "是班级核心学生之一"),
                (r"为年级.{0,6}(做事|付出|做|服务)", lambda m: "积极参与年级事务"),
                (r"愿意.{0,4}(做|帮忙|做事|参与)", lambda m: "做事积极主动"),
            ],
            "integrator": lambda observations: integrate_social(observations)
        },
        "特色与潜能": {
            "analyzers": [
                (r"领导|带领|组织", lambda m: "具有组织领导潜质"),
                (r"最喜欢|特别欣赏|最欣赏", lambda m: "是老师特别关注的学生"),
                (r"做事最多|贡献最多", lambda m: "在集体中贡献突出"),
                (r"创新|创意|点子", lambda m: "思维活跃富有创意"),
                (r"特长|擅长|才艺", lambda m: "具有突出才艺特长"),
                (r"独特|与众不同", lambda m: "有独特的个人特质"),
                (r"潜力|天赋", lambda m: "有较大发展潜力"),
            ],
            "integrator": lambda observations: integrate_potential(observations)
        }
    }

    rules = dim_understanding.get(dimension, {})
    analyzers = rules.get("analyzers", [])

    # 逐条分析
    observations = []
    seen = set()
    for pattern, analyzer in analyzers:
        match = re.search(pattern, text)
        if match:
            obs = analyzer(match)
            if obs and obs not in seen:
                observations.append(obs)
                seen.add(obs)

    if not observations:
        return generic_summarize(text)

    # 使用维度整合器，把零散观察串成人物画像
    integrator = rules.get("integrator")
    if integrator and len(observations) >= 2:
        return integrator(observations)

    return "；".join(observations)


def generic_summarize(text):
    """通用归纳：真正的语义提炼，不是简单截断"""
    # 先做深度口语净化
    cleaned = clean_oral_text(text)

    # 过渡句检测
    transition_patterns = [
        r"^(最后|然后|接着|接下来).{0,3}(说|讲|聊聊|提).{0,3}一下.{0,5}$",
        r"^.{0,5}(吧|了)$",
    ]
    for tp in transition_patterns:
        if re.match(tp, cleaned.strip()):
            return "（过渡语，无实质信息）"

    # 用更广泛的模式匹配来提炼核心意思
    summary_patterns = [
        # 成绩相关
        (r"满分(\d+)分.{0,5}拿到?(\d+)分", lambda m: f"考试成绩优秀（{m.group(2)}/{m.group(1)}分）"),
        (r"成绩.{0,5}(稳定|很好|不错|优秀|厉害)", lambda m: f"学业成绩{m.group(1)}"),
        (r"(语文|数学|英语|科学).{0,10}(全面发展|都好|优秀)", lambda m: f"{m.group(1)}等学科全面发展"),
        (r"成绩(最好|第一|拔尖)", lambda m: "学业成绩在班级拔尖"),
        (r"班级.{0,8}(第二|第三|前[二三])", lambda m: "学业成绩稳居班级前列"),
        (r"(\d+)分.{0,5}拿到?(\d+)分", lambda m: f"考试成绩优秀（{m.group(2)}/{m.group(1)}分）"),
        # 性格/态度相关
        (r"(开朗|活泼|阳光|乐观|积极)", lambda m: f"性格{m.group(1)}"),
        (r"(成熟|稳重|长大)", lambda m: "逐渐成熟稳重"),
        (r"(好胜|要强|争强|不服输)", lambda m: "好胜心强，自尊心高"),
        (r"(自尊心|要面子|好面子)", lambda m: "自尊心较强"),
        (r"(赌气|生气|发脾气|不满)", lambda m: "遇到挫折时容易赌气"),
        (r"(争辩|反驳|顶嘴|不服)", lambda m: "遇到不同意见时容易争辩"),
        # 活动相关
        (r"(帮|愿意).{0,5}(老师|班级|同学).{0,5}(做事|做事情|帮忙)", lambda m: "乐于为班级和老师做事"),
        (r"(十佳|奖|荣誉|称号)", lambda m: "获得过重要荣誉"),
        (r"(乐器|打鼓|音乐|绘画|运动|体育)", lambda m: f"有{m.group(1)}等才艺特长"),
        # 社交相关
        (r"(没|不).{0,5}(选|投票|推荐)", lambda m: "对落选等结果反应强烈"),
        (r"(记住|记仇|报复)", lambda m: "对人际冲突印象深刻"),
        (r"(大队委员|班委|干部|代表)", lambda m: "关注班干部角色"),
        # 生活习惯
        (r"(没|不).{0,5}(上瘾|沉迷|手机|游戏)", lambda m: "生活自律，未沉迷电子产品"),
        (r"睡.{0,4}(早|规律|好)", lambda m: "作息规律"),
        (r"生活.{0,4}(习惯|规律|好)", lambda m: "生活习惯良好"),
        # 家庭环境
        (r"家.{0,8}(和睦|温暖|支持|氛围好)", lambda m: "家庭环境温暖有支持"),
        # 口语化整体评价
        (r"不错.{0,2}不错|真的不错", lambda m: "各方面表现良好"),
        (r"很好.{0,2}很好", lambda m: "整体发展良好"),
        # 活泼+不靠谱
        (r"活泼.{0,8}不靠谱", lambda m: "性格活泼但不够靠谱"),
        (r"太活泼", lambda m: "性格过于活泼"),
        # 领头/核心
        (r"领头|三个人.{0,4}领头", lambda m: "是班级核心学生之一"),
        # 外表
        (r"瘦瘦|瘦", lambda m: "体型偏瘦"),
        (r"黑黑|黑", lambda m: "肤色偏黑"),
        (r"变声期", lambda m: "正处于变声期"),
        # 师生关系
        (r"(和|跟).{0,4}老师.{0,6}(缓和|改善|好|不错|融洽)", lambda m: "师生关系改善"),
        (r"不对着干|不顶撞|不再.{0,4}(对着干|顶撞|对抗)", lambda m: "对抗行为减少"),
        (r"听话|配合|守规矩", lambda m: "变得更加配合"),
        (r"调皮", lambda m: "性格调皮"),
        (r"再好不过", lambda m: "发展态势很好"),
    ]

    for pattern, handler in summary_patterns:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return handler(match)
            except:
                continue

    # 智能截取：提取核心陈述
    result = re.sub(r"^(包括|而且|但是|不过|然后|同时|另外|当然了)\s*", "", cleaned)
    sentences = re.split(r'[，。！？；]', result)
    core_sentences = []
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 4:
            continue
        if s.startswith("比如说") or s.startswith("类似于"):
            continue
        if re.match(r"^(最后|然后|接着|接下来).{0,3}(说|讲|聊聊)", s):
            continue
        core_sentences.append(s)
        if len(core_sentences) >= 2:
            break

    if core_sentences:
        result = "，".join(core_sentences)
        if len(result) > 60:
            result = result[:60]
        return result

    # 最终兜底
    return cleaned[:50] if cleaned else text.strip()[:50]


def summarize_text(text, dimension):
    """
    核心能力：将口语化的长段话归纳为精炼的结构化描述
    PythonAnywhere免费版无LLM API，直接使用增强版规则引擎
    """
    return summarize_text_rules(text, dimension)


# ===== 学生匹配 =====

def match_students(text):
    """从文本中匹配学生名字"""
    data = get_data()
    students = data.get("students", [])
    matched = []
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            matched.append(name)
    return matched


# ===== 核心解析：智能拆分+归纳 =====

def parse_long_text_to_records(text, student_names):
    """
    将一段长文本智能拆分为多条结构化记录
    每条记录都是经过归纳提炼的，不是原话照搬
    """
    # 1. 识别学生
    student = None
    for name in student_names:
        if name in text:
            student = name
            break

    if not student:
        return None, "未能识别到班级学生姓名，请确认姓名是否正确。"

    # 2. 提取日期
    record_date = extract_date_from_text(text)

    # 3. 按语义切分为多个片段
    segments = split_into_segments(text)

    # 4. 对每个片段：分类维度 + 归纳提炼
    records = []
    now_ms = int(datetime.now().timestamp() * 1000)

    for i, seg in enumerate(segments):
        if not seg.strip() or len(seg.strip()) < 3:
            continue

        # 过滤纯过渡句
        stripped = seg.strip()
        if re.match(r'^(最后|然后|接着|接下来|还有).{0,3}(说|讲|聊聊|提).{0,3}一下.{0,5}[吧啊呢]?$', stripped):
            continue
        if len(stripped) < 8:
            continue

        dimension = classify_dimension(seg)
        summary = summarize_text(seg, dimension)

        # 避免重复归纳
        is_dup = False
        for existing in records:
            if existing["summary"] == summary:
                is_dup = True
                break
        if is_dup:
            continue

        record = {
            "id": str(now_ms + i),
            "student": student,
            "date": record_date,
            "dimension": dimension,
            "description": seg.strip(),
            "summary": summary,
            "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }
        records.append(record)

    # 5. 如果只产出1条记录但原文很长，尝试按维度强制拆分
    if len(records) <= 1 and len(text) > 50:
        records = force_split_by_dimension(text, student, record_date, now_ms)

    return records, None


def force_split_by_dimension(text, student, date, base_id):
    """当自动切分不够时，按维度强制拆分"""
    dim_scores = {}
    for dim in DIMENSION_RULES:
        dim_scores[dim] = score_text_for_dimension(text, dim)

    active_dims = [(dim, score) for dim, score in dim_scores.items() if score > 0]
    active_dims.sort(key=lambda x: x[1], reverse=True)

    if not active_dims:
        return [{
            "id": str(base_id),
            "student": student,
            "date": date,
            "dimension": "个人成长",
            "description": text.strip(),
            "summary": generic_summarize(text),
            "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }]

    records = []
    for i, (dim, score) in enumerate(active_dims):
        relevant_sentences = []
        sentences = re.split(r'[，。！？；、\n]', text)
        for s in sentences:
            s = s.strip()
            if not s or len(s) < 3:
                continue
            if score_text_for_dimension(s, dim) > 0:
                relevant_sentences.append(s)

        if not relevant_sentences:
            continue

        relevant_text = "，".join(relevant_sentences)
        summary = summarize_text(relevant_text, dim)

        record = {
            "id": str(base_id + i),
            "student": student,
            "date": date,
            "dimension": dim,
            "description": relevant_text,
            "summary": summary,
            "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }
        records.append(record)

    return records if records else [{
        "id": str(base_id),
        "student": student,
        "date": date,
        "dimension": "个人成长",
        "description": text.strip(),
        "summary": generic_summarize(text),
        "recorder": "梁老师",
        "created_at": datetime.now().isoformat()
    }]


# ===== 数据存取 =====

def get_data():
    """从本地JSON文件读取数据"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"students": [], "records": [], "categories": {}}


def save_data(data):
    """保存数据到本地JSON文件"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===== 路由 =====

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory('public', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """返回静态文件"""
    return send_from_directory('public', path)


@app.route('/api/students', methods=['GET'])
def get_students():
    """获取学生列表"""
    data = get_data()
    return jsonify(data)


@app.route('/api/students', methods=['POST'])
def add_student():
    """添加学生"""
    data = get_data()
    new_student = request.json
    if 'students' not in data:
        data['students'] = []
    data['students'].append(new_student)
    save_data(data)
    return jsonify({"ok": True, "student": new_student})


@app.route('/api/records', methods=['GET'])
def get_records():
    """获取记录 - 支持前端过滤参数"""
    data = get_data()
    student = request.args.get('student', '')
    dimension = request.args.get('dimension', '')
    category = request.args.get('category', '')
    date = request.args.get('date', '')

    records = data.get('records', [])
    if student:
        records = [r for r in records if r.get('student') == student]
    if dimension:
        records = [r for r in records if r.get('dimension') == dimension]
    if category:
        records = [r for r in records if r.get('category') == category or r.get('dimension') == category]
    if date:
        records = [r for r in records if r.get('date') == date]

    return jsonify({"records": records})


@app.route('/api/records', methods=['POST'])
def add_record():
    """添加记录"""
    data = get_data()
    new_record = request.json
    new_record['id'] = str(int(time.time() * 1000))
    new_record['created_at'] = datetime.now().isoformat()
    if 'records' not in data:
        data['records'] = []
    data['records'].append(new_record)
    save_data(data)
    return jsonify({"ok": True, "record": new_record})


@app.route('/api/records/batch', methods=['POST'])
def batch_records():
    """批量保存记录 - 前端确认保存和快速保存都调用这个"""
    data = get_data()
    body = request.json

    if 'records' in body:
        # 从预览确认保存
        records_to_save = body['records']
    elif 'text' in body:
        # 快速保存模式：用语义引擎解析并保存
        text = body['text']
        student_names = [s.get("name", "") for s in data.get("students", []) if s.get("name")]

        records_result, error = parse_long_text_to_records(text, student_names)
        if error:
            return jsonify({"success": False, "error": error}), 400

        records_to_save = records_result if records_result else []
    else:
        return jsonify({"success": False, "error": "参数错误"}), 400

    if 'records' not in data:
        data['records'] = []
    data['records'].extend(records_to_save)
    save_data(data)

    # 自动同步到腾讯文档
    tdoc_msg = ""
    try:
        tdoc_results = tdoc_add_records(records_to_save)
        synced = sum(1 for r in tdoc_results if not r.get("error"))
        tdoc_msg = f"，已同步 {synced} 条到腾讯文档"
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "connection" in err_msg.lower():
            tdoc_msg = "，腾讯文档同步需在本地版操作"
        else:
            tdoc_msg = f"，腾讯文档同步失败: {err_msg[:50]}"

    count = len(records_to_save)
    return jsonify({
        "success": True,
        "message": f"已保存 {count} 条记录{tdoc_msg}",
        "count": count
    })


@app.route('/api/records/<record_id>', methods=['PUT'])
def update_record(record_id):
    """编辑记录"""
    data = get_data()
    records = data.get('records', [])

    for i, r in enumerate(records):
        if str(r.get('id')) == str(record_id):
            body = request.json
            if 'summary' in body:
                records[i]['summary'] = body['summary']
            if 'description' in body:
                records[i]['description'] = body['description']
            if 'dimension' in body:
                records[i]['dimension'] = body['dimension']
            records[i]['updated_at'] = datetime.now().isoformat()
            save_data(data)
            return jsonify({"success": True, "record": records[i]})

    return jsonify({"success": False, "error": "记录不存在"}), 404


@app.route('/api/records/<record_id>', methods=['DELETE'])
def delete_record(record_id):
    """删除记录"""
    data = get_data()
    records = data.get('records', [])

    new_records = [r for r in records if str(r.get('id')) != str(record_id)]
    if len(new_records) < len(records):
        data['records'] = new_records
        save_data(data)
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "记录不存在"}), 404


@app.route('/api/parse', methods=['POST'])
def parse_input():
    """解析自然语言输入 - 使用完整语义解析引擎"""
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "请输入内容"}), 400

    # 获取学生列表
    data = get_data()
    student_names = [s.get("name", "") for s in data.get("students", []) if s.get("name")]

    # 使用核心语义引擎解析
    records_result, error = parse_long_text_to_records(text, student_names)

    if error:
        # 如果语义引擎无法解析，回退到简单匹配
        students = match_students(text)
        dimension = classify_dimension(text)
        date = extract_date_from_text(text)

        records = []
        if students:
            for student in students:
                summary = summarize_text(text, dimension)
                record = {
                    'id': str(int(time.time() * 1000)) + str(hash(student))[-4:],
                    'student': student,
                    'description': text,
                    'summary': summary,
                    'dimension': dimension,
                    'date': date,
                    'created_at': datetime.now().isoformat()
                }
                records.append(record)
        else:
            summary = summarize_text(text, dimension)
            record = {
                'id': str(int(time.time() * 1000)),
                'student': '',
                'description': text,
                'summary': summary,
                'dimension': dimension,
                'date': date,
                'created_at': datetime.now().isoformat()
            }
            records.append(record)

        return jsonify({
            "records": records,
            "message": f"解析完成：识别到 {len(students)} 位学生，归类为「{dimension}」"
        })

    # 语义引擎成功解析
    records = records_result
    # 统计涉及到的维度
    dims_found = list(set(r.get('dimension', '') for r in records))
    student = records[0].get('student', '') if records else ''

    return jsonify({
        "records": records,
        "message": f"解析完成：识别到学生「{student}」，拆分为 {len(records)} 条记录，涉及维度：{'、'.join(dims_found)}"
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据"""
    data = get_data()
    records = data.get('records', [])
    students = data.get('students', [])

    by_dimension = {}
    for dim in DIMENSIONS:
        by_dimension[dim] = 0
    for r in records:
        dim = r.get('dimension', '个人成长')
        if dim in by_dimension:
            by_dimension[dim] += 1
        else:
            by_dimension[dim] = 1

    students_with_records = set(r.get('student', '') for r in records if r.get('student'))
    students_covered = len(students_with_records)

    recent_5 = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)[:5]

    return jsonify({
        "total_records": len(records),
        "total_students": len(students),
        "students_covered": students_covered,
        "by_dimension": by_dimension,
        "recent_5": recent_5
    })


@app.route('/api/report', methods=['GET'])
def get_report():
    """生成学生成长报告"""
    student_name = request.args.get('student', '')
    if not student_name:
        return jsonify({"error": "请指定学生"}), 400

    data = get_data()
    records = data.get('records', [])
    student_records = [r for r in records if r.get('student') == student_name]

    if not student_records:
        return jsonify({"error": f"暂无 {student_name} 的记录"})

    dimensions = {}
    for dim in DIMENSIONS:
        dim_records = [r for r in student_records if r.get('dimension') == dim]
        dimensions[dim] = {
            "count": len(dim_records),
            "records": dim_records
        }

    dim_counts = {dim: dimensions[dim]["count"] for dim in DIMENSIONS}
    strongest = max(dim_counts, key=dim_counts.get)

    summary = f"{student_name}同学共有{len(student_records)}条成长记录。"
    if dim_counts[strongest] > 0:
        summary += f"在「{strongest}」方面表现突出（{dim_counts[strongest]}条记录）。"
    weak_dims = [d for d in DIMENSIONS if dim_counts[d] == 0]
    if weak_dims:
        summary += f"在「{'、'.join(weak_dims)}」方面暂无记录，建议关注。"

    return jsonify({
        "report": {
            "student": student_name,
            "total": len(student_records),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dimensions": dimensions,
            "summary": summary
        }
    })


@app.route('/api/query', methods=['POST'])
def smart_query():
    """智能查询"""
    text = request.json.get('text', '')
    if not text:
        return jsonify({"type": "error", "message": "请输入查询内容"})

    data = get_data()
    records = data.get('records', [])
    students = data.get('students', [])

    matched_students = []
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            matched_students.append(name)

    if matched_students:
        student_name = matched_students[0]
        student_records = [r for r in records if r.get('student') == student_name]

        if not student_records:
            return jsonify({
                "type": "no_data",
                "student": student_name
            })

        dimensions = {}
        for dim in DIMENSIONS:
            dim_records = [r for r in student_records if r.get('dimension') == dim]
            dimensions[dim] = {
                "count": len(dim_records),
                "records": dim_records
            }

        dim_counts = {dim: dimensions[dim]["count"] for dim in DIMENSIONS}
        strongest = max(dim_counts, key=dim_counts.get)
        summary = f"{student_name}同学共有{len(student_records)}条成长记录。"
        if dim_counts[strongest] > 0:
            summary += f"在「{strongest}」方面表现突出（{dim_counts[strongest]}条记录）。"
        weak_dims = [d for d in DIMENSIONS if dim_counts[d] == 0]
        if weak_dims:
            summary += f"在「{'、'.join(weak_dims)}」方面暂无记录，建议关注。"

        return jsonify({
            "type": "report",
            "report": {
                "student": student_name,
                "total": len(student_records),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "dimensions": dimensions,
                "summary": summary
            }
        })

    students_with_records = list(set(r.get('student', '') for r in records if r.get('student')))
    return jsonify({
        "type": "overview",
        "message": f"目前共有 {len(records)} 条记录，{len(students_with_records)} 位学生有记录。",
        "students_with_records": students_with_records
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    data = get_data()
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "students_count": len(data.get('students', [])),
        "records_count": len(data.get('records', []))
    })


# ===== 腾讯文档同步 API =====
# 注意：PA免费版白名单不包含docs.qq.com，同步可能失败
# 代码会尝试调用，成功则同步，失败则提示用户在本地操作

@app.route('/api/tdoc/sync', methods=['POST'])
def tdoc_sync():
    """手动同步所有本地数据到腾讯文档"""
    data = get_data()
    records = data.get('records', [])
    if not records:
        return jsonify({"success": False, "error": "没有记录可同步"})
    try:
        results = tdoc_add_records(records)
        # 检查是否有网络限制错误
        first_error = None
        for r in results:
            if r.get("error"):
                first_error = r.get("error")
                break
        if first_error and ("whitelist" in str(first_error).lower() or "blocked" in str(first_error).lower() or "timed out" in str(first_error).lower()):
            return jsonify({
                "success": False,
                "error": "云端服务器暂无法访问腾讯文档，请在本地版（127.0.0.1:8765）中同步"
            })
        synced = sum(1 for r in results if not r.get("error"))
        failed = len(results) - synced
        msg = f"✅ 已同步 {synced} 条记录到腾讯文档"
        if failed > 0:
            msg += f"（{failed} 条失败）"
        return jsonify({
            "success": True,
            "total": len(records),
            "synced": synced,
            "failed": failed,
            "message": msg,
            "url": TDOC_URL
        })
    except Exception as e:
        err_msg = str(e)
        # 网络受限的典型错误
        if "timed out" in err_msg.lower() or "connection" in err_msg.lower():
            return jsonify({
                "success": False,
                "error": "云端服务器暂无法访问腾讯文档，请在本地版（127.0.0.1:8765）中同步"
            })
        return jsonify({"success": False, "error": f"同步失败: {err_msg}"})


@app.route('/api/tdoc/load', methods=['POST'])
def tdoc_load():
    """从腾讯文档加载记录到本地"""
    try:
        cloud_data = tdoc_list_records()
        if cloud_data.get("error"):
            err_msg = str(cloud_data["error"])
            if "timed out" in err_msg.lower() or "connection" in err_msg.lower():
                return jsonify({
                    "success": False,
                    "error": "云端服务器暂无法访问腾讯文档，请在本地版（127.0.0.1:8765）中加载"
                })
            return jsonify({"success": False, "error": f"加载失败: {cloud_data['error']}"})

        cloud_records = cloud_data.get("records", [])
        if not cloud_records:
            return jsonify({"success": False, "error": "腾讯文档中暂无记录"})

        data = get_data()
        if 'records' not in data:
            data['records'] = []

        # 从腾讯文档记录提取学生姓名等字段
        existing_ids = set(r.get('id', '') for r in data['records'])
        added = 0
        for cr in cloud_records:
            fv = cr.get("field_values", {})
            record = {
                "id": cr.get("record_id", str(int(time.time() * 1000) + added)),
                "student": _extract_text(fv.get("学生姓名", [])),
                "date": _extract_date(fv.get("date", "")),
                "dimension": _extract_option(fv.get("记录维度", [])),
                "summary": _extract_text(fv.get("归纳描述", [])),
                "description": _extract_text(fv.get("原始描述", [])),
                "recorder": _extract_text(fv.get("记录人", [])) or "梁老师",
                "created_at": datetime.now().isoformat()
            }
            if record["student"] and record["id"] not in existing_ids:
                data["records"].append(record)
                existing_ids.add(record["id"])
                added += 1

        save_data(data)
        return jsonify({
            "success": True,
            "added": added,
            "total": len(data["records"]),
            "message": f"✅ 从腾讯文档加载 {added} 条新记录，共 {len(data['records'])} 条"
        })
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "connection" in err_msg.lower():
            return jsonify({
                "success": False,
                "error": "云端服务器暂无法访问腾讯文档，请在本地版（127.0.0.1:8765）中加载"
            })
        return jsonify({"success": False, "error": f"加载失败: {err_msg}"})


def _extract_text(field_val):
    """从腾讯文档字段值中提取文本"""
    if isinstance(field_val, list):
        texts = [item.get("text", "") for item in field_val if isinstance(item, dict)]
        return "".join(texts).strip()
    return str(field_val).strip() if field_val else ""


def _extract_option(field_val):
    """从腾讯文档单选字段中提取选项文本"""
    if isinstance(field_val, list):
        for item in field_val:
            if isinstance(item, dict) and item.get("text"):
                return item["text"]
    return ""


def _extract_date(field_val):
    """从腾讯文档日期字段中提取日期字符串"""
    if isinstance(field_val, (int, float)):
        # 毫秒时间戳转日期
        try:
            dt = datetime.fromtimestamp(field_val / 1000)
            return dt.strftime("%Y-%m-%d")
        except:
            return ""
    if isinstance(field_val, str) and field_val:
        try:
            ts = int(field_val)
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d")
        except:
            return field_val
    return ""


@app.route('/api/cloud/save', methods=['POST'])
def cloud_save():
    return jsonify({"success": False, "error": "云端版暂不支持云端备份，数据已保存在服务器"})


@app.route('/api/cloud/load', methods=['POST'])
def cloud_load():
    return jsonify({"success": False, "error": "云端版暂不支持云端加载，数据已保存在服务器"})


@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    """导出CSV"""
    data = get_data()
    records = data.get('records', [])

    csv_lines = ["学生,维度,归纳总结,原始描述,日期"]
    for r in records:
        student = r.get('student', '')
        dim = r.get('dimension', '')
        summary = r.get('summary', '').replace(',', '，')
        desc = r.get('description', '').replace(',', '，').replace('\n', ' ')
        date = r.get('date', '')
        csv_lines.append(f"{student},{dim},{summary},{desc},{date}")

    csv_content = '\n'.join(csv_lines)
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=class_records.csv'}
    )


@app.route('/api/export/json', methods=['GET'])
def export_json():
    """导出JSON"""
    data = get_data()
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=class_records.json'}
    )


@app.route('/api/import', methods=['POST'])
def import_json():
    """导入JSON数据"""
    body = request.json
    import_data = body.get('data', {})

    if not import_data:
        return jsonify({"success": False, "error": "数据为空"})

    current = get_data()

    if 'students' in import_data and import_data['students']:
        existing_names = {s.get('name') for s in current.get('students', [])}
        for s in import_data['students']:
            if s.get('name') not in existing_names:
                current.setdefault('students', []).append(s)

    if 'records' in import_data and import_data['records']:
        current.setdefault('records', []).extend(import_data['records'])

    save_data(current)
    return jsonify({"success": True, "message": f"导入成功：{len(import_data.get('students', []))}名学生，{len(import_data.get('records', []))}条记录"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
