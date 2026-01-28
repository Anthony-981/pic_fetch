# PicFetch - 超清图片爬取工具

一个功能强大的图片爬取工具，支持从多个来源搜索和下载高清图片。

## 功能特点

- **多图片来源支持**：Unsplash、Pexels、Pixabay 等免费图库
- **智能筛选**：按分辨率、颜色、格式筛选图片
- **GUI 图形界面**：简洁美观的用户界面
- **批量下载**：支持批量下载，自动并发控制
- **EXE 打包**：单文件可执行程序，无需安装 Python

## 截图

![主界面](docs/screenshots/main_window.png)

## 安装

### 方式一：直接下载 EXE（推荐）

1. 从 [Releases](../../releases) 下载最新的 `PicFetch.exe`
2. 双击运行即可使用

### 方式二：从源码运行

#### 1. 克隆项目

```bash
git clone https://github.com/yourusername/pic_fetch.git
cd pic_fetch
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

#### 3. 配置 API 密钥

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 密钥：

```env
UNSPLASH_ACCESS_KEY=your_access_key_here
```

**获取 Unsplash API Key：**
1. 访问 [Unsplash Developers](https://unsplash.com/developers)
2. 注册/登录账号
3. 创建新应用
4. 复制 Access Key

#### 4. 运行程序

```bash
python main.py
```

## 使用方法

### 搜索图片

1. 选择图片来源
2. 输入搜索关键词
3. 点击"搜索"按钮
4. 在预览窗口查看结果

### 下载图片

1. 在预览窗口中点击选择要下载的图片（支持多选）
2. 选择保存目录
3. 点击"下载选中图片"

### 筛选条件

- **分辨率**：FHD (1920x1080)、2K (2560x1440)、4K (3840x2160)
- **格式**：JPG、PNG、WebP
- **颜色**：明亮、暗色、特定颜色

## 开发

### 项目结构

```
pic_fetch/
├── main.py                  # 应用入口
├── config/                  # 配置文件
├── core/                    # 核心模块
│   ├── base_adapter.py      # 适配器基类
│   ├── source_factory.py    # 图片源工厂
│   └── download_manager.py  # 下载管理器
├── sources/                 # 图片源适配器
│   └── unsplash_adapter.py  # Unsplash 适配器
├── gui/                     # GUI 界面
│   └── main_window.py       # 主窗口
├── utils/                   # 工具函数
└── build/                   # 构建配置
    └── pic_fetch.spec       # PyInstaller 配置
```

### 打包成 EXE

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller --clean build/pic_fetch.spec

# 打包后的文件在 dist/PicFetch.exe
```

## 注意事项

### 法律合规

- 仅供个人学习使用
- 遵守各图片来源的使用条款
- 尊重原作者版权
- 不得用于商业用途

### API 限制

- Unsplash 免费版：50 请求/小时
- Pexels 免费版：200 请求/小时
- 请合理控制请求频率

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 致谢

- [Unsplash](https://unsplash.com) - 提供免费高清图片
- [PySide6](https://www.qt.io/qt-for-python) - Qt for Python
- [aiohttp](https://aiohttp.readthedocs.io) - 异步 HTTP 客户端
