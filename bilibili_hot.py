#!/usr/bin/env python3
"""
B站热门视频抓取脚本
通过 B站公开 API 获取全站热门榜 TOP100，生成 Markdown 报告。
部署于 GitHub Actions，定时自动执行。
"""

import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ============ 配置区 ============
# 可选通知方式，通过环境变量控制。留空则不推送，仅生成报告
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 输出目录
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.dirname(os.path.abspath(__file__)))
# ================================

BILIBILI_API = "https://api.bilibili.com/x/web-interface/ranking/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/v/popular/rank/all",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.bilibili.com",
}

# 分区 ID 映射
RID_MAP = {
    "all": 0,
    "animation": 1,
    "music": 3,
    "game": 4,
    "entertainment": 5,
    "tv": 11,
    "tech": 188,
    "life": 160,
    "fashion": 155,
    "sports": 234,
    "documentary": 177,
    "movie": 23,
}


def fetch_ranking(rid: int = 0, top_n: int = 100) -> list:
    """获取 B站热门视频榜单"""
    params = {"rid": rid, "type": "all"}
    try:
        resp = requests.get(BILIBILI_API, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"[ERROR] API 返回异常: {data.get('message', '未知错误')}")
            return []
        video_list = data.get("data", {}).get("list", [])
        return video_list[:top_n]
    except requests.RequestException as e:
        print(f"[ERROR] 请求失败: {e}")
        return []


def format_number(n: int) -> str:
    """格式化数字，超过1万显示为 万"""
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


def generate_report(videos: list, rid_name: str = "全站") -> str:
    """生成 Markdown 格式报告"""
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# B站{rid_name}热门视频 TOP{len(videos)}",
        f"",
        f"> 更新时间: {now}（北京时间）",
        f"> 数据来源: [Bilibili 热门榜](https://www.bilibili.com/v/popular/rank/all)",
        f"",
        f"| 排名 | 标题 | UP主 | 播放 | 弹幕 | 点赞 | 硬币 |",
        f"| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for i, v in enumerate(videos, 1):
        title = v.get("title", "").replace("|", "｜")
        bvid = v.get("bvid", "")
        up_name = v.get("owner", {}).get("name", "未知")
        stat = v.get("stat", {})
        view = format_number(stat.get("view", 0))
        danmaku = format_number(stat.get("danmaku", 0))
        like = format_number(stat.get("like", 0))
        coin = format_number(stat.get("coin", 0))

        video_url = f"https://www.bilibili.com/video/{bvid}"
        lines.append(
            f"| {i} | [{title}]({video_url}) | {up_name} | {view} | {danmaku} | {like} | {coin} |"
        )

    return "\n".join(lines)


def send_telegram(text: str):
    """推送到 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("[OK] Telegram 推送成功")
        else:
            print(f"[WARN] Telegram 推送失败: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Telegram 推送异常: {e}")


def build_wecom_md(videos: list, rid_name: str) -> str:
    """构建企业微信 markdown 消息，手机端友好可点击链接（前15条）"""
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).strftime("%m-%d %H:%M")

    lines = [f"**B站{rid_name}热门榜 TOP15**  |  {now}", ""]
    for i, v in enumerate(videos[:15], 1):
        title = v.get("title", "")
        bvid = v.get("bvid", "")
        up_name = v.get("owner", {}).get("name", "未知")
        stat = v.get("stat", {})
        view = format_number(stat.get("view", 0))
        like = format_number(stat.get("like", 0))
        url = f"https://www.bilibili.com/video/{bvid}"
        lines.append(f"**{i}.** [{title}]({url})")
        lines.append(f"> UP: {up_name}    ▶{view}    ❤{like}")
        lines.append("")
    lines.append(f"数据来源: [Bilibili 热门榜](https://www.bilibili.com/v/popular/rank/all)")
    return "\n".join(lines)


def send_wecom(text: str):
    """推送到企业微信机器人"""
    if not WECOM_WEBHOOK:
        return
    payload = {"msgtype": "markdown", "markdown": {"content": text}}
    try:
        resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=15)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("[OK] 企业微信推送成功")
        else:
            print(f"[WARN] 企业微信推送失败: {resp.text}")
    except Exception as e:
        print(f"[ERROR] 企业微信推送异常: {e}")


def build_feishu_card(videos: list, rid_name: str) -> dict:
    """构建飞书 interactive 卡片消息体（前15条）"""
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M")

    lines = []
    for i, v in enumerate(videos[:15], 1):
        title = v.get("title", "")
        bvid = v.get("bvid", "")
        up_name = v.get("owner", {}).get("name", "未知")
        stat = v.get("stat", {})
        view = format_number(stat.get("view", 0))
        like = format_number(stat.get("like", 0))
        lines.append(
            f"{i}. [{title}](https://www.bilibili.com/video/{bvid})  **{up_name}**  ▶{view}  👍{like}"
        )

    text_body = "\n".join(lines)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"B站{rid_name}热门视频 TOP15"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": text_body}},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": f"数据来源: Bilibili 热门榜 | 更新时间: {now}"}
                    ],
                },
            ],
        },
    }


def send_feishu(payload: dict):
    """推送到飞书机器人"""
    if not FEISHU_WEBHOOK:
        return
    try:
        resp = requests.post(
            FEISHU_WEBHOOK, json=payload, timeout=15,
            headers={"Content-Type": "application/json"}
        )
        result = resp.json()
        if resp.status_code == 200 and result.get("code") == 0:
            print("[OK] 飞书推送成功")
        else:
            print(f"[WARN] 飞书推送失败: {resp.text}")
    except Exception as e:
        print(f"[ERROR] 飞书推送异常: {e}")


def main():
    # 解析命令行参数：支持指定分区
    rid_key = sys.argv[1] if len(sys.argv) > 1 else "all"
    rid = RID_MAP.get(rid_key, 0)
    rid_name = {"all": "全站"}.get(rid_key, rid_key)

    print(f"[INFO] 正在获取 B站{rid_name}热门视频...")
    videos = fetch_ranking(rid=rid, top_n=100)

    if not videos:
        print("[ERROR] 未获取到视频数据，退出")
        sys.exit(1)

    print(f"[INFO] 获取到 {len(videos)} 条视频，正在生成报告...")
    report = generate_report(videos, rid_name)

    # 保存报告
    date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    filename = f"bilibili_hot_{rid_key}_{date_str}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[OK] 报告已保存至: {filepath}")

    # 也生成一份 latest.md 方便固定链接引用
    latest_path = os.path.join(OUTPUT_DIR, "bilibili_hot_latest.md")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[OK] 最新报告已保存至: {latest_path}")

    # 可选推送
    if FEISHU_WEBHOOK:
        feishu_payload = build_feishu_card(videos, rid_name)
        send_feishu(feishu_payload)

    if WECOM_WEBHOOK:
        wecom_text = build_wecom_md(videos, rid_name)
        send_wecom(wecom_text)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        top20 = generate_report(videos[:20], rid_name)
        send_telegram(top20)


if __name__ == "__main__":
    main()
