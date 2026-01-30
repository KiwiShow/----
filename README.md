# PBOC 公开市场买断式逆回购业务公告采集助手

这是一个基于 Python Flask 和 Requests 的金融数据采集与展示系统，专门用于自动化抓取中国人民银行（PBOC）公开市场买断式逆回购业务的公告信息，并通过现代化的 Web 界面进行展示。

## 🚀 功能特性

- **自动化爬虫**：
  - 基于 `requests` 和 `BeautifulSoup4` 实现。
  - 支持**增量爬取**：自动检测数据库中已存在的链接，跳过重复内容，提高效率。
  - 智能解析：自动清洗 HTML 标签，处理表格格式，识别发布日期。
  - 反爬策略：随机 User-Agent 和请求延时，降低被封禁风险。

- **Web 可视化界面**：
  - 基于 Flask 框架构建。
  - **现代化 UI**：采用 Bootstrap 5 设计，集成 Inter 字体与 Bootstrap Icons。
  - **响应式布局**：完美适配桌面、平板和移动端设备。
  - **实时交互**：支持前端一键触发爬取任务，AJAX 异步更新统计数据（新增条数、总条数、更新时间），并通过 Toast/Modal 进行友好提示。

- **数据持久化**：
  - 使用 SQLite 数据库 (`data.db`) 存储公告详情。
  - 自动记录并持久化最后一次采集时间 (`last_crawl_time.txt`)。

## 🛠️ 技术栈

- **后端**：Python 3, Flask, SQLite
- **爬虫**：Requests, BeautifulSoup4
- **前端**：HTML5, CSS3, Bootstrap 5, JavaScript (Fetch API)

## 📦 安装与运行

### 1. 克隆或下载项目

确保你已安装 Python 3.8+ 环境。

### 2. 安装依赖

在项目根目录下运行以下命令安装所需依赖库：

```bash
pip install -r requirements.txt
```

### 3. 启动应用

运行 Flask 应用：

```bash
python app.py
```

### 4. 访问系统

启动成功后，浏览器访问：

```
http://127.0.0.1:5001
```

## 📂 项目结构

```text
金融爬虫/
├── app.py                # Flask 主程序，处理 Web 请求和 API
├── crawler.py            # 核心爬虫逻辑，负责抓取和解析数据
├── data.db               # SQLite 数据库文件（自动生成）
├── last_crawl_time.txt   # 记录最后采集时间的文件
├── requirements.txt      # 项目依赖列表
└── templates/
    └── index.html        # 前端页面模板
```

## 📝 注意事项

- **数据库初始化**：首次运行爬虫时会自动创建 `data.db` 数据库及表结构。
- **爬虫频率**：为了减轻目标服务器压力，爬虫内置了随机延时机制。
- **端口**：默认运行在 `5001` 端口，如需修改请编辑 `app.py` 文件底部。