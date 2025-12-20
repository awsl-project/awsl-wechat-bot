# AWSL 微信机器人

> ⚠️ **免责声明：本项目仅供学习交流，请勿用于商业或违规用途。使用本项目产生的任何后果由使用者自行承担。**

基于 macOS Accessibility API 和 Windows UI Automation 的微信群聊机器人，支持 AI 智能回答和动态命令执行。

## 功能特性

- **跨平台支持**：支持 macOS 和 Windows 10/11 平台
- **原生消息读取**：
  - macOS: 使用 Accessibility API 直接读取微信消息（100% 准确）
  - Windows: 使用 UI Automation 直接读取控件（100% 准确）
- 队列模式架构，消息检测与处理分离，防止漏掉回复
- 智能消息去重机制，基于上下文的哈希算法（前2条消息）
- 优化的消息处理策略，只处理最后3条消息，避免重复触发
- 自动监控指定微信群聊消息
- 检测到 "awsl+问题" 时使用 AI 智能回答问题
- 动态命令系统，从远程 API 加载和执行自定义命令
- 支持 "awsl hp" 特殊命令显示可用命令列表
- 支持冷却时间防止刷屏（10秒）
- SQLite 数据库去重，避免重复响应
- 使用 Pydantic Settings 管理配置
- DEBUG 模式，便于调试和问题排查
- 纯 Python 实现，无需额外服务

## 系统要求

### macOS
- macOS 10.15+ (Catalina 或更高版本)
- 微信 macOS 客户端
- 辅助功能权限（用于模拟键盘操作）

### Windows
- Windows 10 / 11
- 微信 Windows 客户端
- 建议以管理员身份运行终端

### 共同要求
- Python 3.9+

## 安装

1. 克隆项目并进入目录：

```bash
cd awsl-wechat-bot
```

2. 创建虚拟环境并激活：

**macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 配置

### 方式一：使用环境变量（推荐）

1. 复制配置模板文件：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入实际配置：
```bash
# 群聊名称
GROUP_NAME=你的群聊名称

# OpenAI API 配置（必填）
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 命令 API 地址（可选）
COMMAND_API_BASE_URL=https://bhwa233-api.vercel.app

# 调试模式（可选，默认关闭）
DEBUG=false
```

### 方式二：直接修改 config.py

编辑 `config.py` 文件中的默认值：

```python
class Config(BaseSettings):
    # 要监控的群聊名称
    GROUP_NAME: str = "你的群聊名称"

    # 触发关键词
    TRIGGER_KEYWORD: str = "awsl"

    # 检查消息间隔（秒）
    CHECK_INTERVAL: int = 3

    # 触发冷却时间（秒）
    TRIGGER_COOLDOWN: int = 10

    # 命令 API 地址
    COMMAND_API_BASE_URL: str = "https://bhwa233-api.vercel.app"

    # 调试模式
    DEBUG: bool = False

    # OpenAI 配置
    OPENAI_API_KEY: str  # 必须通过环境变量设置
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
```

**注意**：`OPENAI_API_KEY` 必须通过环境变量设置，不应该硬编码在代码中。

## 使用方法

### 1. 前置准备

1. 启动微信并登录
2. 权限设置：
   - **macOS**: 打开「系统设置」→「隐私与安全性」→「辅助功能」，添加并允许「终端」或你使用的终端应用。
   - **Windows**: 建议以管理员身份运行 PowerShell 或 CMD，以确保有足够的权限操作微信窗口。

### 2. 运行机器人

直接运行机器人：

```bash
python main.py
```

机器人会自动：
- 激活微信窗口
- 切换到配置的群聊（Windows 下会使用 Ctrl+F 搜索）
- 点击输入框确保焦点
- 开始监控消息（每3秒检测一次）
- 检测到 "awsl+问题" 时使用 AI 回答
- 检测到 "awsl hp" 时显示命令列表
- 检测到动态命令时执行相应操作

### 3. 使用示例

**AI 智能回答：**
```
用户: awsl今天天气怎么样？
机器人: [AI 回复天气相关信息]

用户: awsl 1+1等于几？
机器人: 1+1等于2！数学界的经典双人舞，永远默契无间。

用户: awsl帮我写一首诗
机器人: [AI 生成诗歌]
```
**注意**：纯 "awsl"（后面没有文本）不会触发任何响应，只有 "awsl+问题" 才会触发 AI。

**动态命令（从远程 API 加载）：**
```
用户: awsl hp
机器人: [显示可用命令列表并刷新命令缓存]

用户: <命令名> <参数>
机器人: [执行相应命令并返回结果]
```

**注意**：
- 动态命令**不需要** awsl 前缀，直接输入命令名即可
- "awsl hp" 是特殊命令，用于显示命令列表和刷新命令缓存
- 命令会在机器人启动时自动从配置的 API 地址加载
- 命令列表和功能由远程 API 动态提供
- 启用 DEBUG 模式可查看详细的命令匹配和执行日志

## 项目结构

```
awsl-wechat-bot/
├── main.py                      # 主程序入口和机器人逻辑
├── config.py                    # 配置文件（使用 Pydantic Settings）
├── ai_service.py                # AI 服务模块
├── command_service.py           # 动态命令服务模块
├── adapters/                    # 平台适配器
│   ├── base.py                  # 适配器基类
│   ├── macos.py                 # macOS 实现 (Accessibility API)
│   └── windows.py               # Windows 实现 (UI Automation)
├── utils_accessibility_api.py   # Accessibility API 工具 (macOS)
├── utils_ocr.py                 # OCR 相关工具（备用）
├── utils_screenshot.py          # 截图工具（备用）
├── get_messages.applescript     # 获取消息的 AppleScript
├── requirements.txt             # Python 依赖
├── .env                         # 环境变量配置（不提交到 Git）
├── .env.example                 # 环境变量配置模板
├── messages.db                  # 消息去重数据库（自动生成）
└── venv/                        # Python 虚拟环境
```

## 工作原理

### 架构设计

机器人使用**双线程队列模式**：

1. **检测线程**：持续监控消息（每3秒一次）
   - 调用对应平台的适配器读取微信聊天消息
   - 只检查最后3条消息，提高效率
   - 使用前向上下文（前2条消息）计算哈希值去重
   - 智能过滤：找到最后一个已处理的消息，只处理其后的新消息
   - 检测到触发关键词时将消息加入队列
   - 使用 SQLite 数据库去重，避免重复处理

2. **处理线程**：从队列取出消息并处理
   - 带冷却控制（10秒），防止刷屏
   - 优先检查是否为动态命令
   - 根据触发类型发送图片或 AI 回复
   - 线程安全的数据库和冷却时间管理

### 消息处理策略

采用**基于上下文的智能去重**：

1. **只处理最后3条消息**：从消息列表中取最后3条，其他消息忽略
2. **前向上下文哈希**：使用前2条消息作为上下文计算哈希值，确保消息唯一性
3. **智能过滤机制**：
   - 预检查：计算这3条消息的哈希值，检查是否已处理
   - 从后往前查找：找到最后一个已处理的消息位置
   - 只处理位置：只触发"最后已处理消息"之后的所有新消息
   - 避免遗漏和重复处理

**示例场景**（假设检查最后3条消息，索引为 0, 1, 2）：
```
[0:新, 1:已处理, 2:新]     → 最后已处理位置=1，处理消息2
[0:已处理, 1:新, 2:新]     → 最后已处理位置=0，处理消息1和2
[0:新, 1:新, 2:已处理]     → 最后已处理位置=2（最后一条），无需处理
[0:新, 1:新, 2:新]         → 无已处理消息，处理所有3条
[0:已处理, 1:已处理, 2:新] → 最后已处理位置=1，处理消息2
```

### 消息获取

**macOS:**
- 使用 macOS Accessibility API 直接访问微信 UI 元素
- 查找 AXList（title="Messages"）获取消息列表
- 提取每条消息的 AXStaticText 内容
- 准确度 100%，无需 OCR

**Windows:**
- 使用 Microsoft UI Automation (via `uiautomation` 库)
- 查找 `ListControl`（Name="消息"）获取消息列表
- 提取 `ListItemControl` 下的文本内容
- 准确度 100%，无需 OCR

### 输入框焦点

**macOS:**
- 使用 Quartz 框架的系统级鼠标事件
- 计算输入框位置（窗口宽度60%，高度92%）
- 模拟真实鼠标点击获得焦点

**Windows:**
- 使用 UI Automation 激活窗口
- 发送消息时使用 `Ctrl+F` 确保在群聊界面，使用 `Ctrl+V` 粘贴消息

### 智能响应

机器人支持多种响应模式：

1. **纯 "awsl"**：不触发任何响应
2. **"awsl+文本"**（非 hp）：调用 OpenAI API 获取 AI 回复并发送
3. **"awsl hp"**：特殊命令，显示可用命令列表并刷新命令缓存
4. **动态命令**：直接输入命令名（无需 awsl 前缀），调用远程 API 执行

命令优先级：
- 首先检查是否为 "awsl hp" 特殊命令
- 其次检查是否以 "awsl" 开头（触发 AI）
- 最后检查是否匹配动态命令（无需前缀）

## 注意事项

- 首次运行需要授予相关权限（macOS 辅助功能 / Windows 管理员）
- 运行时微信窗口需要保持可见（不能最小化到托盘）
- 机器人运行期间会自动激活微信窗口
- 建议在不使用电脑时运行，避免影响其他操作
- **推荐使用虚拟机运行**，可实现隔离环境和 24/7 持续运行

## DEBUG 模式

启用 DEBUG 模式可以获得详细的运行日志，便于排查问题：

```bash
# 在 .env 文件中设置
DEBUG=true
```

DEBUG 模式会输出：
- 每次检测到的所有消息内容
- 消息的哈希值计算过程
- 前向上下文预览（前2条消息）
- 消息处理状态（新消息/已处理）
- 命令匹配和执行的详细过程
- 最后已处理消息的位置
- 触发逻辑的判断过程

**建议**：生产环境关闭 DEBUG 模式以减少日志输出，仅在调试时开启。

## 免责声明

**本项目仅供学习交流使用，请勿用于商业用途或任何违法违规行为。**

- 本项目是一个技术学习和研究项目，旨在探索 macOS Accessibility API 和 Windows UI Automation 技术
- 使用本项目时请遵守微信的使用条款和相关法律法规
- 开发者不对使用本项目造成的任何后果负责
- 请勿将本项目用于：
  - 发送垃圾信息或骚扰他人
  - 传播违法违规内容
  - 任何商业盈利目的
  - 其他可能违反微信使用条款的行为
- 如因使用本项目产生任何问题，责任由使用者自行承担

**By using this project, you agree that you understand these terms and will use it responsibly for educational purposes only.**

## 许可证

MIT License