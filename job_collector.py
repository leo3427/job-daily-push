import feedparser
import requests
import json
import os
import smtplib
from email.mime.text import MIMEText

# ==================================================
# 个人配置区（核心参数已填入，可直接使用）
# ==================================================
# 1. 简历匹配关键词（机器人工程+锂电设备+汽车制造背景）
MATCH_KEYWORDS = [
    "设备工程师", "工艺工程师", "自动化工程师", "设备运维", "技术支持工程师",
    "PLC", "机器视觉", "CCD", "电芯", "锂电", "锂电池", "汽车制造",
    "工业机器人", "制程工程师", "设备助理", "自动化设备", "机电设备",
    "生产技术", "设备维护", "视觉检测","半导体","机械","非标设备","管培生",
    "实习","工程师","助理工程师"
]

# 2. 硬性排除关键词（命中直接过滤）
BLACKLIST = [
    # 作息黑名单
    "单休", "月休4天", "每月休息4天", "做六休一", "每月休4天",
    # 四级硬性要求黑名单
    "必须四级", "硬性要求四级", "CET-4必备", "英语四级硬性要求",
    "四级证书必备", "要求英语四级证书", "需持有英语四级证书"
]

# 3. 预警关键词（不直接排除，推送时标注提醒）
WARN_KEYWORDS = ["四级", "CET-4", "英语四级", "英语优先", "英语良好"]

# 4. 应届生&本科学历筛选规则
# 正向匹配：命中即符合应届生/本科身份
GRADUATE_KEYWORDS = ["应届生", "应届毕业生", "校招", "校园招聘", "2026届", "应届", "毕业生"]
EDUCATION_KEYWORDS = ["本科", "本科生", "本科及以上", "本科学历", "全日制本科", "大专及以上"]
# 反向排除：命中直接过滤（社招、高学历要求）
EXP_BLACKLIST = ["1年以上经验", "2年以上", "3年以上", "5年以上", "工作经验要求", "社招", "社会招聘"]
EDU_BLACKLIST = ["硕士及以上", "研究生学历", "硕士学历", "要求硕士", "博士"]

# 5. 公开招聘数据源（RSS格式，已补充江西本地源）
RSS_URLS = [
    # 国家24365大学生就业平台-全国招聘会RSS
    "https://job.ncss.cn/student/rss/jobfair.xml",
    # 江西省大学生就业服务平台（覆盖全省高校校招）
    "https://jxdxsjy.jx.edu.cn/juwp/rss.xml",
    # 江西水利电力大学校园招聘（FetchRSS生成后替换此处）
    "【这里替换成你生成的江西水利电力大学RSS链接】",
    # 上饶市人社局招聘（FetchRSS生成后替换此处）
    "【这里替换成你生成的上饶人社局RSS链接】",
]

# 6. 邮箱推送配置（已填入你的QQ邮箱信息）
SENDER_EMAIL = "3202775630@qq.com"
EMAIL_AUTH_CODE = os.environ.get("EMAIL_AUTH_CODE", "")
RECEIVER_EMAIL = "3202775630@qq.com"

# 7. 微信推送配置（已填入你的Server酱SendKey）
SERVER_CHAN_KEY = os.environ.get("SERVER_CHAN_KEY", "")
# 8. 去重历史记录文件（无需修改）
HISTORY_FILE = "pushed_jobs_history.json"
# ==================================================
# 配置区结束，以下无需修改
# ==================================================

def load_history():
    """加载已推送岗位历史，用于去重"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_history(history_set):
    """保存最新推送历史"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(history_set), f, ensure_ascii=False, indent=2)

def match_filter(title, content):
    """
    核心筛选逻辑
    返回：(是否通过, 预警信息)
    """
    full_text = title + content

    # 第一步：通用黑名单硬性排除
    for word in BLACKLIST:
        if word in full_text:
            return False, ""
    
    # 第二步：排除社招、高学历要求岗位
    for word in EXP_BLACKLIST:
        if word in full_text:
            return False, ""
    for word in EDU_BLACKLIST:
        if word in full_text:
            return False, ""

    # 第三步：简历方向匹配（至少命中1个核心关键词）
    match_count = sum(1 for k in MATCH_KEYWORDS if k in full_text)
    if match_count < 1:
        return False, ""

    # 第四步：应届生&本科学历匹配
    # 放宽规则：校招/校园招聘专场默认符合身份要求
    is_campus = any(k in full_text for k in ["校园招聘", "校招"])
    is_graduate = any(k in full_text for k in GRADUATE_KEYWORDS)
    is_edu_ok = any(k in full_text for k in EDUCATION_KEYWORDS)
    # 满足：(校招专场) 或者 (应届生标识 + 学历符合) 即可通过
    if not is_campus and not (is_graduate and is_edu_ok):
        return False, ""

    # 第五步：四级预警标记
    warn_info = ""
    if any(k in full_text for k in WARN_KEYWORDS):
        warn_info = "⚠️ 提及英语四级，需人工确认是否为硬性要求"

    return True, warn_info

def send_email(html_content):
    """发送HTML格式邮件推送"""
    if not SENDER_EMAIL or not EMAIL_AUTH_CODE:
        print("未配置邮箱，跳过邮件推送")
        return
    try:
        msg = MIMEText(html_content, "html", "utf-8")
        msg["Subject"] = "【每日岗位推送】应届生本科+匹配简历+无硬性四级+非单休"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL

        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SENDER_EMAIL, EMAIL_AUTH_CODE)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print("邮件推送成功")
    except Exception as e:
        print(f"邮件推送失败：{e}")

def send_wechat(title, content):
    """通过Server酱推送微信"""
    if not SERVER_CHAN_KEY:
        print("未配置Server酱，跳过微信推送")
        return
    try:
        url = f"https://sctapi.ftqq.com/{SERVER_CHAN_KEY}.send"
        data = {"title": title, "desp": content}
        requests.post(url, data=data, timeout=10)
        print("微信推送成功")
    except Exception as e:
        print(f"微信推送失败：{e}")

def main():
    # 加载历史去重数据
    history = load_history()
    new_valid_jobs = []

    # 遍历所有数据源拉取岗位
    for source_url in RSS_URLS:
        # 跳过未替换的占位链接
        if "【" in source_url or "】" in source_url:
            continue
        try:
            feed = feedparser.parse(source_url)
            for entry in feed.entries:
                job_title = entry.get("title", "无标题岗位")
                job_summary = entry.get("summary", "无简介")
                job_link = entry.get("link", "")

                # 去重：已推送过的岗位直接跳过
                if job_link and job_link in history:
                    continue

                # 执行筛选规则
                is_pass, warn = match_filter(job_title, job_summary)
                if not is_pass:
                    continue

                # 加入有效岗位列表
                new_valid_jobs.append({
                    "title": job_title,
                    "link": job_link,
                    "summary": job_summary[:300],
                    "warn": warn
                })

                # 记录到去重历史
                if job_link:
                    history.add(job_link)

        except Exception as e:
            print(f"数据源解析失败 [{source_url}]：{e}")

    # 生成推送内容
    if not new_valid_jobs:
        email_html = "<h3>今日暂无符合全部筛选条件的新岗位</h3>"
        wechat_text = "今日暂无符合条件的新岗位"
    else:
        # 邮件HTML内容
        email_html = f"<h2>今日新增符合条件岗位：{len(new_valid_jobs)} 个</h2>"
        # 微信纯文本内容
        wechat_text = f"今日新增 {len(new_valid_jobs)} 个符合条件岗位\n\n"

        for idx, job in enumerate(new_valid_jobs, 1):
            # 邮件内容
            email_html += f"""
            <div style="margin:15px 0; padding:12px; border:1px solid #e5e5e5; border-radius:6px;">
                <h4 style="margin:0 0 8px 0;">{idx}. {job['title']}</h4>
                <p style="margin:4px 0;">岗位链接：<a href="{job['link']}" target="_blank">{job['link']}</a></p>
                <p style="margin:4px 0; color:#333;">简介：{job['summary']}...</p>
                {f'<p style="margin:4px 0; color:#ff8c00; font-weight:bold;">{job["warn"]}</p>' if job['warn'] else ''}
            </div>
            """
            # 微信内容
            wechat_text += f"{idx}. {job['title']}\n链接：{job['link']}\n{job['warn']}\n\n"

    # 执行双渠道推送
    send_email(email_html)
    send_wechat(f"每日岗位推送（{len(new_valid_jobs)}个新岗）", wechat_text)

    # 保存去重历史
    # save_history(history)
    print(f"运行完成，今日新增符合条件岗位：{len(new_valid_jobs)} 个")

if __name__ == "__main__":
    main()
