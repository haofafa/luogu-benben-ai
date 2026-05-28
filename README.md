# 洛谷犇犇AI自动回复系统

基于AI的洛谷犇犇自动回复机器人，支持图片识别、管理员过滤、Web控制面板。

**警告：使用本脚本可能导致洛谷账号被封禁，作者概不负责！**

## 功能特点

- AI自动回复洛谷犇犇（支持多模态图片识别）
- 可配置回复频率（默认每3条回1条，模拟真人行为）
- 可配置检查间隔（默认10秒）
- 自动过滤管理员，不回复提及管理员的犇犇
- 15秒节奏控制（0秒检查 → 生成回复 → 7秒发送 → 15秒完成）
- Web控制面板（支持中英切换、深色模式）
- 自动从洛谷更新管理员名单

## 系统要求

- Debian 12
- Python 3.9+
- 可访问洛谷和AI API的网络环境

## 推荐AI模型

推荐使用360智脑的 `bytedance/doubao-seed-2-0-mini` 模型：

1. 访问 [360智脑开放平台](https://ai.360.com/open) 注册账号
2. 申领API（公司可填"无公司"或"个人"等）
3. 新用户可免费领取50元额度
4. 创建API Key并填入配置文件

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/haofafa/luogu-benben-ai.git
cd luogu-benben-ai
```

### 2. 配置参数

编辑 `luogu_ai.py`，找到 `Config` 类，修改以下配置：

```python
class Config:
    # AI API配置（推荐360智脑免费领取50元额度：https://ai.360.com/open）
    API_KEY = "你的API密钥"
    API_BASE = "https://api.360.cn/v1"
    MODEL = "bytedance/doubao-seed-2-0-mini"
    
    # 洛谷账号Cookie（从浏览器F12获取）
    USER = "你的洛谷用户名"
    COOKIES = {
        "__client_id": "从浏览器获取",
        "_uid": "从浏览器获取",
        "C3VK": "从浏览器获取"
    }
    
    # 回复频率配置
    INTERVAL = 10  # 检查间隔(秒)，在 run() 函数中生效
    RATIO = 3      # 回复比例，每3条回1条，在 should_reply() 函数中生效
    MAX_LEN = 30   # AI回复最大字数，在 gen_reply() 函数中生效
    
    # Web控制面板配置
    PWD = "设置你的管理密码"       # 控制面板登录密码
    SECRET = "随便填一串乱码"      # Flask session加密密钥
```

### 3. Cookie获取方法

1. 浏览器登录 [洛谷](https://www.luogu.com.cn)
2. 按 `F12` 打开开发者工具
3. 进入 `Application` → `Cookies` → `www.luogu.com.cn`
4. 复制 `__client_id`、`_uid`、`C3VK` 的值

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 启动服务

```bash
chmod +x start.sh stop.sh
./start.sh
```

### 6. 停止服务

```bash
./stop.sh
```

### 7. 访问控制面板

浏览器打开 `http://服务器IP:11451`

- 默认语言：中文
- 切换英文：`http://IP:11451?lang=en`
- 深色模式：`http://IP:11451?theme=dark`

## 配置说明

### 回复频率调整

| 参数 | 位置 | 说明 | 默认值 |
|------|------|------|--------|
| `INTERVAL` | `Config` 类 → `_schedule_worker()` | 检查新犇犇的间隔 | 10秒 |
| `RATIO` | `Config` 类 → `should_reply()` | 每N条回复1条 | 3 |
| `MAX_LEN` | `Config` 类 → `gen_reply()` | AI回复最大字数 | 30字 |

**调高频率（更容易封号）**：
```python
INTERVAL = 5   # 5秒检查一次
RATIO = 1      # 每条都回复
```

**调低频率（更安全）**：
```python
INTERVAL = 30  # 30秒检查一次
RATIO = 5      # 每5条回复1条
```

### 15秒节奏说明

`run()` 函数中的节奏控制：

```
0秒  → 获取犇犇列表
      → AI生成回复
7秒  → 发送回复（模拟人类阅读+打字时间）
15秒 → 本轮结束
```

## 警告

**使用本脚本可能导致洛谷账号被封禁！**

- 使用前请自行评估风险
- 建议降低回复频率以减少风险
- 作者不对任何账号封禁负责

## 管理员名单

系统会自动从洛谷获取管理员名单并定期更新，以下用户默认加入管理员列表：

洛谷, 洛谷视频题解, 洛谷网校, kkksc03, soha, hh0592821, cleverdango, 冬天的忧郁, chen_zhe, 一扶苏一, Maxmilite

包含以上用户的犇犇不会被回复。

## 项目结构

```
luogu-benben-ai/
├── luogu_ai.py          # 主程序
├── start.sh             # 启动脚本
├── stop.sh              # 停止脚本
├── requirements.txt     # Python依赖
└── README.md           # 说明文档
```

## 免责声明

本工具仅供学习交流使用，请勿用于违反洛谷社区规则的行为。使用者需自行承担一切后果。
