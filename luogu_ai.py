#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
洛谷犇犇AI自动回复系统
"""

import os
import sys
import json
import time
import threading
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from functools import wraps
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from openai import OpenAI
import schedule

# 配置日志
LOG_DIR = Path('/www/wwwroot/luogu_ai')
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'luogu_ai.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Config:
    """配置文件"""
    API_KEY = "your_api_key_here"
    API_BASE = "https://api.360.cn/v1"
    MODEL = "your_model_name"
    
    USER = "your_username"
    COOKIES = {
        "__client_id": "your_client_id",
        "_uid": "your_uid",
        "C3VK": "your_c3vk"
    }
    
    INTERVAL = 10
    RATIO = 3
    MAX_LEN = 30
    BASE_DIR = LOG_DIR
    DATA_FILE = BASE_DIR / 'replied_feeds.json'
    SKIP_FILE = BASE_DIR / 'skip_count.json'
    ADMIN_FILE = BASE_DIR / 'admin_list.json'
    MAX_RETRY = 3
    RETRY_DELAY = 3
    
    PWD = "your_admin_password"
    SECRET = "your_secret_key"
    
    ADMIN_LIST = [
        "洛谷", "洛谷视频题解", "洛谷网校", "kkksc03", "soha",
        "hh0592821", "cleverdango", "冬天的忧郁", "chen_zhe",
        "一扶苏一", "Maxmilite"
    ]

class AdminManager:
    """管理员名单管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.list = set(config.ADMIN_LIST)
        self.last_update = None
        self.update_interval = 3600
        self.lock = threading.Lock()
        self.load()
        logger.info(f"管理员名单初始化完成，当前 {len(self.list)} 人")
    
    def load(self):
        try:
            if os.path.exists(self.config.ADMIN_FILE):
                with open(self.config.ADMIN_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.list.update(data.get('admins', []))
                    self.last_update = data.get('last_update')
        except Exception as e:
            logger.error(f"加载管理员名单失败: {e}")
    
    def save(self):
        try:
            data = {
                'admins': list(self.list),
                'last_update': datetime.now().isoformat(),
                'count': len(self.list)
            }
            with open(self.config.ADMIN_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存管理员名单失败: {e}")
    
    def fetch(self) -> bool:
        try:
            logger.info("正在从洛谷获取管理员名单...")
            url = 'https://www.luogu.com.cn/judgement/admins'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', {'id': 'lentille-context'})
            
            if script_tag:
                data = json.loads(script_tag.string)
                admins_data = data.get('data', {}).get('admins', {})
                
                new_list = set()
                for role, admin_list in admins_data.items():
                    for admin in admin_list:
                        name = admin.get('name')
                        if name:
                            new_list.add(name)
                
                new_list.update(self.config.ADMIN_LIST)
                
                with self.lock:
                    self.list = new_list
                    self.last_update = datetime.now()
                    
                logger.info(f"管理员名单更新完成，当前 {len(self.list)} 人")
                self.save()
                return True
            else:
                logger.error("未找到管理员数据")
                return False
        except Exception as e:
            logger.error(f"获取管理员名单失败: {e}")
            return False
    
    def is_admin(self, user: str) -> bool:
        if not user:
            return False
        if user in self.list:
            return True
        user_lower = user.lower()
        for admin in self.list:
            if admin.lower() == user_lower:
                return True
        return False
    
    def get_all(self) -> List[str]:
        with self.lock:
            return sorted(list(self.list))
    
    def should_update(self) -> bool:
        if not self.last_update:
            return True
        try:
            last = datetime.fromisoformat(self.last_update)
            return (datetime.now() - last).total_seconds() > self.update_interval
        except:
            return True

class LuoguAI:
    """洛谷AI自动回复系统"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            api_key=config.API_KEY,
            base_url=config.API_BASE
        )
        self.session = requests.Session()
        self.replied = self.load_replied()
        self.skip = self.load_skip()
        self.admin = AdminManager(config)
        self.running = True
        self.interval = config.INTERVAL
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.luogu.com.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        
        for key, value in config.COOKIES.items():
            self.session.cookies.set(key, value)
        
        self.thread = threading.Thread(target=self._schedule_worker, daemon=True)
        self.thread.start()
        
        self.admin_thread = threading.Thread(target=self._admin_update_worker, daemon=True)
        self.admin_thread.start()
        
        logger.info(f"LuoguAI初始化完成")
        logger.info(f"用户名: {config.USER}")
        logger.info(f"模型: {config.MODEL}")
        logger.info(f"检查间隔: {self.interval}秒")
        logger.info(f"回复比例: 每{config.RATIO}条回1条")

    def load_replied(self) -> Set[str]:
        try:
            if os.path.exists(self.config.DATA_FILE):
                with open(self.config.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('replied_feeds', []))
        except Exception as e:
            logger.error(f"加载回复记录失败: {e}")
        return set()

    def save_replied(self):
        try:
            data = {
                'replied_feeds': list(self.replied),
                'last_update': datetime.now().isoformat(),
                'total_count': len(self.replied)
            }
            with open(self.config.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存回复记录失败: {e}")

    def load_skip(self) -> int:
        try:
            if os.path.exists(self.config.SKIP_FILE):
                with open(self.config.SKIP_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('skip_count', 0)
        except:
            pass
        return 0

    def save_skip(self):
        try:
            with open(self.config.SKIP_FILE, 'w', encoding='utf-8') as f:
                json.dump({'skip_count': self.skip}, f)
        except Exception as e:
            logger.error(f"保存跳过计数失败: {e}")

    def should_reply(self) -> bool:
        self.skip += 1
        self.save_skip()
        
        if self.skip >= self.config.RATIO:
            self.skip = 0
            self.save_skip()
            return True
        return False

    def get_token(self) -> Optional[str]:
        try:
            response = self.session.get('https://www.luogu.com.cn/feed', timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            token_meta = soup.find('meta', {'name': 'csrf-token'})
            if token_meta:
                return token_meta.get('content')
        except Exception as e:
            logger.error(f"获取CSRF Token失败: {e}")
        return None

    def get_imgs(self, html: str) -> List[str]:
        imgs = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            img_tags = soup.find_all('img')
            
            for img in img_tags:
                src = img.get('src', '')
                if src and 'usericon' not in src.lower():
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://www.luogu.com.cn' + src
                    
                    if src.startswith('http'):
                        imgs.append(src)
        except Exception as e:
            logger.error(f"提取图片失败: {e}")
        
        return imgs

    def get_feeds(self) -> List[Dict]:
        feeds = []
        try:
            url = 'https://www.luogu.com.cn/feed/watching?page=1'
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            feed_elements = soup.find_all('li', class_='feed-li')
            logger.info(f"找到 {len(feed_elements)} 条犇犇")
            
            for feed in feed_elements:
                try:
                    user_elem = feed.select_one('.feed-username a')
                    content_elem = feed.select_one('.feed-comment p')
                    report_link = feed.find('a', {'name': 'feed-report'})
                    
                    if not user_elem or not content_elem or not report_link:
                        continue
                    
                    username = user_elem.text.strip()
                    content_html = str(content_elem)
                    content_text = content_elem.text.strip()
                    fid = report_link.get('data-report-id')
                    
                    imgs = self.get_imgs(content_html)
                    
                    if username != self.config.USER and fid not in self.replied:
                        feeds.append({
                            'user': username,
                            'content': content_text,
                            'html': content_html,
                            'id': fid,
                            'imgs': imgs
                        })
                except Exception as e:
                    logger.debug(f"解析犇犇失败: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"获取犇犇失败: {e}")
        
        return feeds

    def has_admin(self, text: str) -> bool:
        try:
            for admin in self.admin.get_all():
                if not admin:
                    continue
                admin_lower = admin.lower()
                text_lower = text.lower()
                
                if admin_lower in text_lower:
                    logger.info(f"发现管理员提及: '{admin}'")
                    return True
                
                at_pattern = f"@{admin}"
                if re.search(at_pattern, text, re.IGNORECASE):
                    logger.info(f"发现管理员@提及: '{admin}'")
                    return True
            return False
        except Exception as e:
            logger.error(f"检查管理员提及时出错: {e}")
            return False

    def clean_text(self, text: str) -> str:
        try:
            text = re.sub(r'<[^>]+>', '', text)
            import html
            text = html.unescape(text)
            text = text.replace('\n', ' ').replace('\r', ' ')
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:300]
        except:
            return text[:300]

    def gen_reply(self, feed: Dict) -> Optional[str]:
        try:
            if self.has_admin(feed['content']):
                logger.warning(f"内容提及管理员，跳过回复")
                return None
            
            clean_content = self.clean_text(feed['content'])
            imgs = feed.get('imgs', [])
            
            prompt = f"""你是一个洛谷用户，正在刷犇犇。看到一条犇犇，请用简短自然的口语回复（不超过30字）。要求：
1. 简体中文，简洁随意，像真人聊天
2. 可以吐槽、附和、提问或发表看法
3. 不要用表情符号和颜文字
4. 不要@任何人
5. 不要说"回复："之类的前缀
6. 如果对方发了图片，可以评论图片内容

对方：{feed['user']}
内容："{clean_content}"
"""
            if imgs:
                prompt += f"\n对方还发了 {len(imgs)} 张图片。"

            msgs = [{"role": "user", "content": []}]
            
            msgs[0]["content"].append({
                "type": "text",
                "text": prompt
            })
            
            for img_url in imgs[:3]:
                msgs[0]["content"].append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })
            
            if not imgs:
                msgs = [{"role": "user", "content": prompt}]
            
            logger.info(f"调用AI生成回复...")
            
            response = self.client.chat.completions.create(
                model=self.config.MODEL,
                messages=msgs,
                max_tokens=100,
                temperature=0.9,
                timeout=30
            )
            
            reply = response.choices[0].message.content.strip()
            reply = reply.replace('"', '').replace("'", "").strip()
            
            prefixes = ["回复：", "回复:", "回复 ", "答：", "答:", "答 "]
            for prefix in prefixes:
                if reply.startswith(prefix):
                    reply = reply[len(prefix):].strip()
            
            emoji_pattern = re.compile("["
                u"\U0001F600-\U0001F64F"
                u"\U0001F300-\U0001F5FF"
                u"\U0001F680-\U0001F6FF"
                u"\U0001F1E0-\U0001F1FF"
                "]+", flags=re.UNICODE)
            reply = emoji_pattern.sub(r'', reply)
            
            if len(reply) > self.config.MAX_LEN * 2:
                reply = reply[:self.config.MAX_LEN * 2]
            
            logger.info(f"AI生成回复: {reply}")
            
            full_reply = f"{reply} || @{feed['user']} : {feed['content']}"
            return full_reply
            
        except Exception as e:
            logger.error(f"AI生成回复失败: {e}")
            return None

    def send_reply(self, content: str) -> bool:
        for attempt in range(self.config.MAX_RETRY):
            try:
                logger.info(f"发送回复 (尝试 {attempt + 1}/{self.config.MAX_RETRY})")
                
                token = self.get_token()
                if not token:
                    logger.error("无法获取CSRF Token")
                    continue
                
                headers = {
                    'X-CSRF-Token': token,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Origin': 'https://www.luogu.com.cn',
                    'Referer': 'https://www.luogu.com.cn/feed/watching?page=1'
                }
                
                for key, value in headers.items():
                    self.session.headers[key] = value
                
                data = {'content': content}
                
                response = self.session.post(
                    'https://www.luogu.com.cn/api/feed/postBenben',
                    data=data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('status') == 200:
                        logger.info(f"发送成功!")
                        return True
                    else:
                        logger.error(f"发送失败: {result}")
                else:
                    logger.error(f"HTTP错误: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"发送失败: {e}")
            
            if attempt < self.config.MAX_RETRY - 1:
                time.sleep(self.config.RETRY_DELAY)
        
        return False

    def run(self):
        if not self.running:
            return
        
        logger.info("=" * 60)
        logger.info(f"开始新一轮... (跳过计数: {self.skip}/{self.config.RATIO})")
        
        try:
            t0 = time.time()
            feeds = self.get_feeds()
            
            if not feeds:
                logger.info("没有新犇犇")
                logger.info("=" * 60)
                return
            
            target = None
            for feed in feeds:
                if feed['id'] not in self.replied:
                    target = feed
                    break
            
            if not target:
                logger.info("所有犇犇已回复")
                logger.info("=" * 60)
                return
            
            logger.info(f"新犇犇 #{target['id']} @{target['user']}: {target['content'][:80]}...")
            
            should_reply = self.should_reply()
            
            if not should_reply:
                logger.info(f"跳过（计数={self.skip}）")
                self.replied.add(target['id'])
                self.save_replied()
                
                elapsed = time.time() - t0
                remain = max(0, 15 - elapsed)
                if remain > 0:
                    time.sleep(remain)
                logger.info("本轮结束（跳过）")
                logger.info("=" * 60)
                return
            
            logger.info(f"命中！准备回复")
            
            reply = self.gen_reply(target)
            
            if not reply:
                logger.info(f"跳过（提及管理员或生成失败）")
                self.replied.add(target['id'])
                self.save_replied()
                
                elapsed = time.time() - t0
                remain = max(0, 15 - elapsed)
                if remain > 0:
                    time.sleep(remain)
                logger.info("本轮结束")
                logger.info("=" * 60)
                return
            
            elapsed = time.time() - t0
            wait = max(0, 7 - elapsed)
            if wait > 0:
                logger.info(f"等待 {wait:.1f}秒...")
                time.sleep(wait)
            
            if self.send_reply(reply):
                self.replied.add(target['id'])
                self.save_replied()
                logger.info(f"已回复")
            else:
                logger.error(f"发送失败")
            
            elapsed_total = time.time() - t0
            remain = max(0, 15 - elapsed_total)
            if remain > 0:
                time.sleep(remain)
            
        except Exception as e:
            logger.error(f"处理出错: {e}")
        
        logger.info("本轮结束")
        logger.info("=" * 60)

    def stop(self):
        self.running = False
        logger.info("正在停止服务...")

    def _schedule_worker(self):
        logger.info(f"定时任务启动，间隔: {self.interval}秒")
        self.run()
        schedule.every(self.interval).seconds.do(self.run)
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logger.error(f"定时任务出错: {e}")
                time.sleep(10)

    def _admin_update_worker(self):
        while self.running:
            try:
                if self.admin.should_update():
                    self.admin.fetch()
                time.sleep(1800)
            except Exception as e:
                logger.error(f"管理员更新线程出错: {e}")
                time.sleep(300)

# Flask应用
app = Flask(__name__)
app.secret_key = Config.SECRET
ai = None

# 多语言文本
TEXT = {
    'zh': {
        'title': '控制面板',
        'login_title': '管理登录',
        'login': '登录',
        'logout': '退出登录',
        'password': '密码',
        'wrong_pwd': '密码错误',
        'dashboard': '控制面板',
        'processed': '已处理',
        'feeds': '条犇犇',
        'interval': '检查间隔',
        'seconds': '秒',
        'skip_count': '跳过计数',
        'next_reply': '回复',
        'next_skip': '跳过',
        'admins': '管理员',
        'protected': '人',
        'controls': '控制中心',
        'run_once': '立即执行',
        'stop': '停止服务',
        'update_admins': '更新管理员',
        'reset': '重置记录',
        'reset_skip': '重置跳过',
        'not_init': '系统未初始化',
        'started': '已开始执行',
        'stopped': '服务已停止',
        'reset_done': '记录已重置',
        'skip_reset': '跳过计数已重置',
        'update_ok': '更新成功',
        'update_fail': '更新失败',
    },
    'en': {
        'title': 'Dashboard',
        'login_title': 'Admin Login',
        'login': 'Login',
        'logout': 'Logout',
        'password': 'Password',
        'wrong_pwd': 'Wrong password',
        'dashboard': 'Dashboard',
        'processed': 'Processed',
        'feeds': 'feeds',
        'interval': 'Interval',
        'seconds': 's',
        'skip_count': 'Skip Count',
        'next_reply': 'reply',
        'next_skip': 'skip',
        'admins': 'Admins',
        'protected': 'protected',
        'controls': 'Controls',
        'run_once': 'Run Once',
        'stop': 'Stop',
        'update_admins': 'Update Admins',
        'reset': 'Reset Records',
        'reset_skip': 'Reset Skip',
        'not_init': 'System not initialized',
        'started': 'Started',
        'stopped': 'Stopped',
        'reset_done': 'Records reset',
        'skip_reset': 'Skip count reset',
        'update_ok': 'Updated',
        'update_fail': 'Update failed',
    }
}

def get_lang() -> str:
    """获取当前语言"""
    lang = request.args.get('lang', session.get('lang', 'zh'))
    if lang not in ('zh', 'en'):
        lang = 'zh'
    session['lang'] = lang
    return lang

def need_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ t.login_title }}</title>
    <style>
        :root {
            --bg: #fafafa;
            --card-bg: #fff;
            --text: #333;
            --text-secondary: #999;
            --border: #eee;
            --input-bg: #fafafa;
            --btn-bg: #333;
            --btn-text: #fff;
            --btn-hover: #555;
        }
        .dark {
            --bg: #1a1a2e;
            --card-bg: #16213e;
            --text: #e0e0e0;
            --text-secondary: #888;
            --border: #2a2a4a;
            --input-bg: #0f3460;
            --btn-bg: #e94560;
            --btn-text: #fff;
            --btn-hover: #c73e54;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s;
        }
        .box {
            background: var(--card-bg);
            padding: 40px;
            border: 1px solid var(--border);
            width: 320px;
            transition: all 0.3s;
        }
        h2 {
            text-align: center;
            margin-bottom: 30px;
            font-weight: 300;
            letter-spacing: 2px;
        }
        input {
            width: 100%;
            padding: 10px;
            margin: 8px 0;
            border: 1px solid var(--border);
            background: var(--input-bg);
            color: var(--text);
            font-size: 14px;
            outline: none;
            transition: all 0.3s;
        }
        input:focus {
            border-color: var(--text-secondary);
        }
        button {
            width: 100%;
            padding: 10px;
            background: var(--btn-bg);
            color: var(--btn-text);
            border: none;
            font-size: 14px;
            cursor: pointer;
            margin-top: 20px;
            transition: all 0.3s;
        }
        button:hover {
            background: var(--btn-hover);
        }
        .error {
            color: #e74c3c;
            font-size: 13px;
            text-align: center;
            margin-top: 10px;
        }
        .toggle-bar {
            position: fixed;
            top: 10px;
            right: 10px;
            display: flex;
            gap: 5px;
        }
        .toggle-btn {
            padding: 5px 10px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text);
            cursor: pointer;
            font-size: 12px;
            transition: all 0.3s;
            margin: 0;
            width: auto;
        }
        .toggle-btn:hover {
            border-color: var(--text-secondary);
        }
        .toggle-btn.active {
            background: var(--btn-bg);
            color: var(--btn-text);
            border-color: var(--btn-bg);
        }
    </style>
</head>
<body class="{{ 'dark' if request.args.get('theme') == 'dark' else '' }}">
    <div class="toggle-bar">
        <a href="?lang=zh&theme={{ request.args.get('theme', '') }}" class="toggle-btn {{ 'active' if lang == 'zh' else '' }}">中</a>
        <a href="?lang=en&theme={{ request.args.get('theme', '') }}" class="toggle-btn {{ 'active' if lang == 'en' else '' }}">EN</a>
        <a href="?lang={{ lang }}&theme={{ 'light' if request.args.get('theme') == 'dark' else 'dark' }}" class="toggle-btn">{{ '亮' if lang == 'zh' else 'Light' if request.args.get('theme') == 'dark' else '暗' if lang == 'zh' else 'Dark' }}</a>
    </div>
    <div class="box">
        <h2>{{ t.login_title }}</h2>
        <form method="POST">
            <input type="password" name="pwd" placeholder="{{ t.password }}" required>
            <button type="submit">{{ t.login }}</button>
        </form>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </div>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ t.dashboard }}</title>
    <style>
        :root {
            --bg: #fafafa;
            --card-bg: #fff;
            --text: #333;
            --text-secondary: #999;
            --border: #eee;
            --btn-bg: #fff;
            --btn-text: #666;
            --btn-border: #ddd;
            --btn-hover-bg: #fafafa;
            --btn-hover-border: #999;
            --btn-hover-text: #333;
            --log-bg: #1a1a1a;
            --log-text: #0f0;
        }
        .dark {
            --bg: #1a1a2e;
            --card-bg: #16213e;
            --text: #e0e0e0;
            --text-secondary: #888;
            --border: #2a2a4a;
            --btn-bg: #16213e;
            --btn-text: #ccc;
            --btn-border: #2a2a4a;
            --btn-hover-bg: #0f3460;
            --btn-hover-border: #e94560;
            --btn-hover-text: #e94560;
            --log-bg: #0a0a1a;
            --log-text: #00ff88;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 20px;
            transition: all 0.3s;
        }
        .wrap { max-width: 1200px; margin: 0 auto; }
        .head {
            background: var(--card-bg);
            padding: 20px;
            border: 1px solid var(--border);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s;
        }
        .head h1 {
            font-size: 20px;
            font-weight: 300;
            letter-spacing: 1px;
        }
        .head-right {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .toggle-bar {
            display: flex;
            gap: 5px;
        }
        .toggle-btn {
            padding: 5px 10px;
            background: var(--btn-bg);
            border: 1px solid var(--btn-border);
            color: var(--btn-text);
            cursor: pointer;
            font-size: 12px;
            text-decoration: none;
            transition: all 0.3s;
        }
        .toggle-btn:hover {
            border-color: var(--btn-hover-border);
            color: var(--btn-hover-text);
        }
        .toggle-btn.active {
            background: var(--btn-hover-text);
            color: #fff;
            border-color: var(--btn-hover-text);
        }
        .logout {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 14px;
            padding: 5px 10px;
            border: 1px solid var(--btn-border);
            transition: all 0.3s;
        }
        .logout:hover {
            color: var(--text);
            border-color: var(--btn-hover-border);
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .card {
            background: var(--card-bg);
            padding: 20px;
            border: 1px solid var(--border);
            transition: all 0.3s;
        }
        .card h3 {
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 400;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .card .val {
            font-size: 28px;
            font-weight: 300;
            color: var(--text);
        }
        .card .sub {
            color: var(--text-secondary);
            font-size: 11px;
            margin-top: 5px;
            opacity: 0.7;
        }
        .ctrl {
            background: var(--card-bg);
            padding: 20px;
            border: 1px solid var(--border);
            margin-bottom: 20px;
            transition: all 0.3s;
        }
        .ctrl h2 {
            color: var(--text);
            margin-bottom: 15px;
            font-size: 16px;
            font-weight: 300;
            letter-spacing: 1px;
        }
        .btns {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 8px 16px;
            border: 1px solid var(--btn-border);
            background: var(--btn-bg);
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--btn-text);
        }
        .btn:hover {
            border-color: var(--btn-hover-border);
            color: var(--btn-hover-text);
            background: var(--btn-hover-bg);
        }
        .log {
            background: var(--log-bg);
            color: var(--log-text);
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
            line-height: 1.6;
            transition: all 0.3s;
        }
    </style>
</head>
<body class="{{ 'dark' if request.args.get('theme') == 'dark' else '' }}">
    <div class="wrap">
        <div class="head">
            <h1>{{ t.dashboard }}</h1>
            <div class="head-right">
                <div class="toggle-bar">
                    <a href="?lang=zh&theme={{ request.args.get('theme', '') }}" class="toggle-btn {{ 'active' if lang == 'zh' else '' }}">中</a>
                    <a href="?lang=en&theme={{ request.args.get('theme', '') }}" class="toggle-btn {{ 'active' if lang == 'en' else '' }}">EN</a>
                    <a href="?lang={{ lang }}&theme={{ 'light' if request.args.get('theme') == 'dark' else 'dark' }}" class="toggle-btn">{{ '亮色' if lang == 'zh' else 'Light' if request.args.get('theme') == 'dark' else '暗色' if lang == 'zh' else 'Dark' }}</a>
                </div>
                <a href="/logout" class="logout">{{ t.logout }}</a>
            </div>
        </div>

        <div class="cards">
            <div class="card">
                <h3>{{ t.processed }}</h3>
                <div class="val">{{ stats.processed }}</div>
                <div class="sub">{{ t.feeds }}</div>
            </div>
            <div class="card">
                <h3>{{ t.interval }}</h3>
                <div class="val">{{ stats.interval }}{{ t.seconds }}</div>
                <div class="sub">check interval</div>
            </div>
            <div class="card">
                <h3>{{ t.skip_count }}</h3>
                <div class="val">{{ stats.skip }}/{{ stats.ratio }}</div>
                <div class="sub">next: {{ t.next_reply if stats.skip == 0 else t.next_skip }}</div>
            </div>
            <div class="card">
                <h3>{{ t.admins }}</h3>
                <div class="val">{{ stats.admins }}</div>
                <div class="sub">{{ t.protected }}</div>
            </div>
        </div>

        <div class="ctrl">
            <h2>{{ t.controls }}</h2>
            <div class="btns">
                <button class="btn" onclick="api('/api/run')">{{ t.run_once }}</button>
                <button class="btn" onclick="api('/api/stop')">{{ t.stop }}</button>
                <button class="btn" onclick="api('/api/update-admins')">{{ t.update_admins }}</button>
                <button class="btn" onclick="api('/api/reset')">{{ t.reset }}</button>
                <button class="btn" onclick="api('/api/reset-skip')">{{ t.reset_skip }}</button>
            </div>
        </div>

        <div class="log" id="log">{{ logs }}</div>
    </div>

    <script>
        function api(url) {
            fetch(url, { method: 'POST' })
                .then(r => r.json())
                .then(d => alert(d.message))
                .then(() => location.reload());
        }
        setInterval(() => {
            fetch('/api/logs')
                .then(r => r.text())
                .then(text => {
                    const el = document.getElementById('log');
                    el.innerHTML = text;
                    el.scrollTop = el.scrollHeight;
                });
        }, 5000);
    </script>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = get_lang()
    t = TEXT[lang]
    error = None
    if request.method == 'POST':
        if request.form.get('pwd') == Config.PWD:
            session['logged_in'] = True
            return redirect(url_for('dashboard', lang=lang, theme=request.args.get('theme', '')))
        else:
            error = t['wrong_pwd']
    return render_template_string(LOGIN_HTML, lang=lang, t=t, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@need_login
def dashboard():
    lang = get_lang()
    t = TEXT[lang]
    
    if not ai:
        return t['not_init']
    
    logs = []
    try:
        with open(LOG_DIR / 'luogu_ai.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()[-30:]
    except:
        logs = [t['not_init']]
    
    log_html = '<br>'.join([l.strip() for l in logs])
    
    stats = {
        'processed': len(ai.replied),
        'interval': ai.interval,
        'skip': ai.skip,
        'ratio': ai.config.RATIO,
        'admins': len(ai.admin.get_all()),
    }
    
    return render_template_string(DASHBOARD_HTML, lang=lang, t=t, stats=stats, logs=log_html)

@app.route('/api/run', methods=['POST'])
@need_login
def api_run():
    lang = get_lang()
    t = TEXT[lang]
    if ai:
        threading.Thread(target=ai.run, daemon=True).start()
        return jsonify({'success': True, 'message': t['started']})
    return jsonify({'success': False, 'message': t['not_init']})

@app.route('/api/stop', methods=['POST'])
@need_login
def api_stop():
    lang = get_lang()
    t = TEXT[lang]
    if ai:
        ai.stop()
        return jsonify({'success': True, 'message': t['stopped']})
    return jsonify({'success': False, 'message': t['not_init']})

@app.route('/api/reset', methods=['POST'])
@need_login
def api_reset():
    lang = get_lang()
    t = TEXT[lang]
    if ai:
        ai.replied.clear()
        ai.save_replied()
        return jsonify({'success': True, 'message': t['reset_done']})
    return jsonify({'success': False, 'message': t['not_init']})

@app.route('/api/reset-skip', methods=['POST'])
@need_login
def api_reset_skip():
    lang = get_lang()
    t = TEXT[lang]
    if ai:
        ai.skip = 0
        ai.save_skip()
        return jsonify({'success': True, 'message': t['skip_reset']})
    return jsonify({'success': False, 'message': t['not_init']})

@app.route('/api/update-admins', methods=['POST'])
@need_login
def api_update_admins():
    lang = get_lang()
    t = TEXT[lang]
    if ai:
        success = ai.admin.fetch()
        if success:
            return jsonify({'success': True, 'message': f"{t['update_ok']}, {len(ai.admin.get_all())} admins"})
        else:
            return jsonify({'success': False, 'message': t['update_fail']})
    return jsonify({'success': False, 'message': t['not_init']})

@app.route('/api/logs')
@need_login
def api_logs():
    try:
        with open(LOG_DIR / 'luogu_ai.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()[-50:]
        return '<br>'.join([log.strip() for log in logs])
    except:
        return 'Cannot read logs'

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'processed': len(ai.replied) if ai else 0,
        'skip': ai.skip if ai else 0
    })

def main():
    global ai
    
    config = Config()
    ai = LuoguAI(config)
    
    ai.admin.fetch()
    
    logger.info("=" * 60)
    logger.info("Luogu AI Reply System Started")
    logger.info(f"User: {config.USER}")
    logger.info(f"Model: {config.MODEL}")
    logger.info("=" * 60)
    
    try:
        from waitress import serve
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress"])
        from waitress import serve
    
    host = '0.0.0.0'
    port = 11451
    
    logger.info(f"Web: http://{host}:{port}")
    
    try:
        serve(app, host=host, port=port, threads=4)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if ai:
            ai.stop()
    except Exception as e:
        logger.error(f"Server failed: {e}")
        raise

if __name__ == '__main__':
    main()