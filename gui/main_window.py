"""
主窗口模块
图片爬取工具的主界面
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QProgressBar,
    QLabel, QComboBox, QPushButton, QSpinBox, QLineEdit,
    QGroupBox, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QCheckBox, QScrollArea, QDialog, QFormLayout, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QUrl
from PySide6.QtGui import QPixmap, QImage, QIcon, QAction, QDesktopServices
from pathlib import Path
from typing import List, Optional
import asyncio
import os
import aiohttp
import aiofiles

from core.base_adapter import ImageInfo, SearchParams, DownloadProgress
from core.source_factory import SourceFactory, SourceManager

# 导入所有适配器以注册它们
import sources.unsplash_adapter
import sources.pexels_adapter
import sources.pixabay_adapter
import sources.wallhaven_adapter
import sources.wallpaperflare_adapter
import sources.bing_adapter
import sources.picsum_adapter
import sources.bing_daily_adapter
import sources.chinese_wallpaper_apis
import sources.sakura_anime_adapter
import sources.test_adapter


class SearchWorker(QThread):
    """搜索工作线程"""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, source_manager, source_name: str, config: dict, params: SearchParams):
        super().__init__()
        self.source_manager = source_manager
        self.source_name = source_name
        self.config = config
        self.params = params

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def do_search():
                adapter = await self.source_manager.get_adapter(self.source_name, config=self.config)
                result = await adapter.search(self.params)
                return result, adapter

            result, adapter = loop.run_until_complete(do_search())
            self.finished.emit((result, adapter))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            loop.close()


class DownloadWorker(QThread):
    """下载工作线程"""
    progress = Signal(str, int, int)  # filename, downloaded, total
    finished = Signal(str, str)  # filename, save_path
    error = Signal(str, str)  # filename, error
    all_finished = Signal()

    def __init__(self, images: List[ImageInfo], save_dir: str):
        super().__init__()
        self.images = images
        self.save_dir = save_dir

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._download_all())
        finally:
            loop.close()
            self.all_finished.emit()

    async def _download_all(self):
        """下载所有图片"""
        os.makedirs(self.save_dir, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            for img in self.images:
                try:
                    await self._download_one(session, img)
                except Exception as e:
                    self.error.emit(img.title, str(e))

    async def _download_one(self, session: aiohttp.ClientSession, img: ImageInfo):
        """下载单张图片"""
        # 生成文件名
        ext = os.path.splitext(img.url)[1] or ".jpg"
        # 清理文件名
        safe_title = "".join(c for c in img.title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title}_{img.width}x{img.height}{ext}"
        if not filename:
            filename = f"image_{os.urandom(4).hex()}{ext}"

        save_path = os.path.join(self.save_dir, filename)

        # 下载
        async with session.get(img.url) as response:
            if response.status == 200:
                total = int(response.headers.get('content-length', 0))
                downloaded = 0

                async with aiofiles.open(save_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(filename, downloaded, total)

                self.finished.emit(filename, save_path)
            else:
                self.error.emit(img.title, f"HTTP {response.status}")


class ImagePreviewWidget(QScrollArea):
    """图片预览组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)

        # 图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                border: 1px solid #444;
            }
        """)
        self.image_label.setText("请选择一张图片预览")

        self.setWidget(self.image_label)
        self.current_image = None

        # 信息标签
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")

    def show_image(self, img: ImageInfo):
        """显示图片"""
        self.current_image = img

        # 显示信息
        info_text = (
            f"标题: {img.title}\n"
            f"来源: {img.source}\n"
            f"尺寸: {img.width}x{img.height}\n"
            f"格式: {img.format}"
        )
        self.image_label.setText(f"正在加载...\n\n{info_text}")

        # 异步加载图片
        self._load_image_async(img.url)

    def _load_image_async(self, url: str):
        """异步加载图片"""
        import threading

        def load_in_thread():
            try:
                import requests
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    img_data = response.content
                    qimg = QImage.fromData(img_data)
                    if qimg.isNull():
                        # 如果直接加载失败，尝试用QPixmap
                        pixmap = QPixmap()
                        if pixmap.loadFromData(img_data):
                            # 缩放图片以适应窗口
                            scaled = pixmap.scaled(
                                self.image_label.size(),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                            # 在主线程更新
                            QTimer.singleShot(0, lambda: self._update_pixmap(scaled))
                        else:
                            QTimer.singleShot(0, lambda: self._show_error("图片格式不支持"))
                    else:
                        # 缩放图片
                        pixmap = QPixmap.fromImage(qimg)
                        scaled = pixmap.scaled(
                            self.image_label.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        QTimer.singleShot(0, lambda: self._update_pixmap(scaled))
                else:
                    QTimer.singleShot(0, lambda: self._show_error(f"加载失败: HTTP {response.status_code}"))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._show_error(f"加载失败: {e}"))

        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()

    def _update_pixmap(self, pixmap: QPixmap):
        """更新显示的图片"""
        img = self.current_image
        if img:
            info_text = (
                f"标题: {img.title}\n"
                f"来源: {img.source}\n"
                f"尺寸: {img.width}x{img.height}\n"
                f"格式: {img.format}"
            )
            self.image_label.setPixmap(pixmap)
            self.info_label.setText(info_text)

    def _show_error(self, message: str):
        """显示错误"""
        if self.current_image:
            info_text = (
                f"标题: {self.current_image.title}\n"
                f"来源: {self.current_image.source}\n"
                f"尺寸: {self.current_image.width}x{self.current_image.height}\n"
                f"格式: {self.current_image.format}\n\n"
                f"预览加载失败\n{message}"
            )
            self.image_label.setText(info_text)

    def clear_image(self):
        """清空图片"""
        self.current_image = None
        self.image_label.clear()
        self.image_label.setText("请选择一张图片预览")
        self.info_label.clear()


class ImageListWidget(QListWidget):
    """图片列表组件"""

    itemSelected = Signal(object)  # ImageInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ListMode)  # 先用列表模式确保能显示
        self.setIconSize(QSize(150, 100))
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(5)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.currentItemChanged.connect(self._on_selection_changed)

    def add_images(self, images: List[ImageInfo]):
        """添加图片到列表"""
        print(f"[DEBUG] ImageListWidget.add_images() 被调用，收到 {len(images)} 张图片")
        for i, img in enumerate(images):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, img)
            item.setText(f"[{img.source}] {img.title[:50]} - {img.width}x{img.height}")
            self.addItem(item)
            if i < 3:  # 只打印前3个
                print(f"[DEBUG] 添加图片 {i+1}: {item.text()}")

        print(f"[DEBUG] 列表现在有 {self.count()} 个项目")

    def _on_double_click(self, item: QListWidgetItem):
        """双击事件"""
        img = item.data(Qt.UserRole)
        if img:
            self.itemSelected.emit(img)

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """选择变化事件"""
        if current:
            img = current.data(Qt.UserRole)
            if img:
                self.itemSelected.emit(img)

    def clear_images(self):
        """清空列表"""
        print(f"[DEBUG] ImageListWidget.clear_images() 被调用")
        self.clear()


class MainWindow(QMainWindow):
    """
    主窗口
    图片爬取工具的主界面
    """

    # 图片源映射
    SOURCE_MAP = {
        # 测试源（无需API Key）
        "测试图片源（推荐）": "test",

        # 国际图库
        "Unsplash（高清网图）": "unsplash",
        "Pexels（免费图库）": "pexels",
        "Pixabay（素材库）": "pixabay",
        "Picsum（随机照片）": "picsum",

        # 壁纸网站
        "Wallhaven（高清壁纸）": "wallhaven",
        "WallpaperFlare（壁纸）": "wallpaperflare",
        "Bing每日壁纸": "bing_daily",

        # 搜索引擎
        "Bing图片搜索": "bing",

        # 中文壁纸API
        "搏天壁纸API": "botian",
        "小歪壁纸API": "xiaowai",
        "360壁纸API": "wallpaper360",
        "姬长信壁纸API": "jichangxin",

        # 动漫壁纸
        "樱花动漫壁纸": "sakura_anime",
    }

    def __init__(self):
        super().__init__()
        self.source_manager = SourceManager()
        self.current_adapter = None
        self.search_results: List[ImageInfo] = []
        self.save_directory = str(Path.home() / "Pictures" / "pic_fetch")

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("图片爬取工具 v1.0")
        self.setGeometry(100, 100, 1400, 900)

        # 中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧面板（搜索+筛选）
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # 右侧面板（预览+队列）
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # 设置分割比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        # 状态栏
        self._create_status_bar()

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 图片源选择
        source_group = QGroupBox("图片来源")
        source_layout = QVBoxLayout()

        self.source_combo = QComboBox()
        self.source_combo.addItems(list(self.SOURCE_MAP.keys()))
        source_layout.addWidget(self.source_combo)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # 搜索面板
        search_group = QGroupBox("浏览图片")
        search_layout = QVBoxLayout()

        # 关键词输入
        search_layout.addWidget(QLabel("关键词（可选）:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("留空直接获取推荐图片...")
        search_layout.addWidget(self.keyword_input)

        # 按钮布局
        btn_layout = QHBoxLayout()

        # 推荐按钮
        self.recommend_btn = QPushButton("推荐精选")
        self.recommend_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        btn_layout.addWidget(self.recommend_btn)

        # 搜索按钮
        self.search_btn = QPushButton("搜索")
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        btn_layout.addWidget(self.search_btn)

        search_layout.addLayout(btn_layout)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # 筛选面板
        filter_group = QGroupBox("筛选条件")
        filter_layout = QVBoxLayout()

        # 分辨率
        filter_layout.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "全部",
            "1920x1080 (FHD)",
            "2560x1440 (2K)",
            "3840x2160 (4K)",
            "7680x4320 (8K)",
        ])
        filter_layout.addWidget(self.resolution_combo)

        # 格式
        filter_layout.addWidget(QLabel("格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["全部", "JPG", "PNG", "WebP"])
        filter_layout.addWidget(self.format_combo)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # 下载设置
        download_group = QGroupBox("下载设置")
        download_layout = QVBoxLayout()

        # 保存目录
        download_layout.addWidget(QLabel("保存目录:"))
        dir_layout = QHBoxLayout()
        self.save_dir_label = QLabel(self.save_directory)
        self.save_dir_label.setWordWrap(True)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setMaximumWidth(80)
        dir_layout.addWidget(self.save_dir_label)
        dir_layout.addWidget(self.browse_btn)
        download_layout.addLayout(dir_layout)

        # 下载数量
        download_layout.addWidget(QLabel("下载数量:"))
        self.download_count_spin = QSpinBox()
        self.download_count_spin.setRange(1, 1000)
        self.download_count_spin.setValue(20)
        download_layout.addWidget(self.download_count_spin)

        # 下载按钮
        self.download_btn = QPushButton("下载选中图片")
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0a6cb8;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        download_layout.addWidget(self.download_btn)

        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # 弹性空间
        layout.addStretch()

        return panel

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        # 使用分割器分隔图片列表和预览
        splitter = QSplitter(Qt.Vertical)

        # 上半部分：图片列表
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        self.result_count_label = QLabel("共 0 张图片")
        toolbar_layout.addWidget(self.result_count_label)
        toolbar_layout.addStretch()
        self.select_all_btn = QPushButton("全选")
        self.clear_selection_btn = QPushButton("取消选择")
        toolbar_layout.addWidget(self.select_all_btn)
        toolbar_layout.addWidget(self.clear_selection_btn)
        list_layout.addLayout(toolbar_layout)

        # 图片列表
        self.image_list = ImageListWidget()
        self.image_list.setMaximumHeight(300)
        list_layout.addWidget(self.image_list)

        splitter.addWidget(list_widget)

        # 下半部分：图片预览
        self.preview_widget = ImagePreviewWidget()
        splitter.addWidget(self.preview_widget)

        # 设置分割比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        return splitter

    def _create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.status_bar.addPermanentWidget(self.progress_bar)

        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def _connect_signals(self):
        """连接信号槽"""
        self.recommend_btn.clicked.connect(self._on_recommend)
        self.search_btn.clicked.connect(self._on_search)
        self.browse_btn.clicked.connect(self._on_browse_directory)
        self.download_btn.clicked.connect(self._on_download)
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.clear_selection_btn.clicked.connect(self._on_clear_selection)

        # 图片选择信号
        self.image_list.itemSelected.connect(self._on_image_selected)

        # 启动时自动加载推荐图片
        QTimer.singleShot(500, self._on_recommend)

    def _get_source_name(self) -> str:
        """获取选择的图片源内部名称"""
        display_name = self.source_combo.currentText()
        return self.SOURCE_MAP.get(display_name, "test")  # 默认使用测试源

    def _on_recommend(self):
        """推荐精选按钮点击"""
        # 使用推荐关键词
        recommend_keywords = {
            "test": "wallpaper",
            "unsplash": "nature landscape",
            "pexels": "nature",
            "pixabay": "landscape",
            "picsum": "random",
            "wallhaven": "scenery",
            "wallpaperflare": "nature",
            "bing_daily": "daily",
            "bing": "wallpaper",
            "botian": "random",
            "xiaowai": "random",
            "wallpaper360": "scenery",
            "jichangxin": "random",
            "sakura_anime": "anime",
        }

        source_name = self._get_source_name()
        keywords = recommend_keywords.get(source_name, "wallpaper")

        self.keyword_input.setText(keywords)
        self._do_search(keywords)

    def _on_search(self):
        """搜索按钮点击"""
        keywords = self.keyword_input.text().strip()
        if not keywords:
            # 如果没有关键词，使用推荐
            self._on_recommend()
            return

        self._do_search(keywords)

    def _do_search(self, keywords: str):
        """执行搜索"""
        self.search_btn.setEnabled(False)
        self.recommend_btn.setEnabled(False)
        self.status_label.setText("正在搜索...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度

        # 获取选择的图片来源
        source_name = self._get_source_name()

        # 获取筛选条件
        resolution = self.resolution_combo.currentText()
        if resolution == "全部":
            resolution = None

        format_filter = self.format_combo.currentText()
        if format_filter == "全部":
            format_filter = None

        # 构建适配器配置
        config = {}
        if source_name == "unsplash":
            config["access_key"] = os.getenv("UNSPLASH_ACCESS_KEY")
        elif source_name == "pexels":
            config["api_key"] = os.getenv("PEXELS_API_KEY")
        elif source_name == "pixabay":
            config["api_key"] = os.getenv("PIXABAY_API_KEY")
        elif source_name == "wallhaven":
            config["api_key"] = os.getenv("WALLHAVEN_API_KEY")
        elif source_name == "bing":
            config["api_key"] = os.getenv("BING_API_KEY")

        print(f"[DEBUG] 使用图片源: {source_name}")
        print(f"[DEBUG] 关键词: {keywords}")

        params = SearchParams(
            keywords=keywords,
            per_page=30,
            resolution=resolution,
            format=format_filter.lower() if format_filter else None
        )

        # 使用 SearchWorker
        self.search_worker = SearchWorker(self.source_manager, source_name, config, params)
        self.search_worker.finished.connect(self._on_search_finished)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.start()

    def _on_search_finished(self, result):
        """搜索完成"""
        results, adapter = result
        self.current_adapter = adapter
        self.search_results = results

        print(f"[DEBUG] 找到 {len(results)} 张图片")
        self._update_search_results(results)
        self._search_finished()

    def _on_search_error(self, error_msg: str):
        """搜索错误"""
        print(f"[ERROR] 搜索失败: {error_msg}")
        self._show_error(f"搜索失败: {error_msg}")

    def _update_search_results(self, results: List[ImageInfo]):
        """更新搜索结果"""
        print(f"[DEBUG] _update_search_results() 被调用，收到 {len(results)} 张图片")
        self.image_list.clear_images()

        if not results:
            self.result_count_label.setText("共 0 张图片")
            self.status_label.setText("未找到图片，请尝试其他关键词或图片源")
            QMessageBox.information(self, "提示", "未找到图片，请尝试：\n1. 更换关键词\n2. 选择其他图片源\n3. 检查网络连接")
            return

        self.image_list.add_images(results)
        self.result_count_label.setText(f"共 {len(results)} 张图片")
        self.status_label.setText(f"找到 {len(results)} 张图片")
        print(f"[DEBUG] UI更新完成")

    def _search_finished(self):
        """搜索完成"""
        self.search_btn.setEnabled(True)
        self.recommend_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("就绪")

    def _show_error(self, message: str):
        """显示错误"""
        self.search_btn.setEnabled(True)
        self.recommend_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "错误", message)
        self.status_label.setText("错误")

    def _on_browse_directory(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择保存目录",
            self.save_directory
        )
        if directory:
            self.save_directory = directory
            self.save_dir_label.setText(directory)

    def _on_download(self):
        """下载按钮点击"""
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要下载的图片")
            return

        images = [
            item.data(Qt.UserRole)
            for item in selected_items
            if item.data(Qt.UserRole)
        ]

        self.status_label.setText(f"准备下载 {len(images)} 张图片...")

        # 创建下载目录
        os.makedirs(self.save_directory, exist_ok=True)

        # 启动下载线程
        self.download_worker = DownloadWorker(images, self.save_directory)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_one_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.all_finished.connect(self._on_download_all_finished)
        self.download_worker.start()

    def _on_download_progress(self, filename: str, downloaded: int, total: int):
        """下载进度"""
        if total > 0:
            percent = int(downloaded / total * 100)
            self.status_label.setText(f"下载中: {filename} - {percent}%")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        else:
            self.status_label.setText(f"下载中: {filename} - {downloaded} bytes")

    def _on_download_one_finished(self, filename: str, save_path: str):
        """单张图片下载完成"""
        print(f"[DEBUG] 下载完成: {filename} -> {save_path}")

    def _on_download_error(self, filename: str, error: str):
        """下载错误"""
        print(f"[ERROR] 下载失败: {filename} - {error}")

    def _on_download_all_finished(self):
        """所有下载完成"""
        self.progress_bar.setVisible(False)
        self.status_label.setText("下载完成！")
        QMessageBox.information(
            self,
            "完成",
            f"图片已保存到:\n{self.save_directory}\n\n点击确定打开文件夹",
            QMessageBox.Ok
        )
        # 打开文件夹
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.save_directory))

    def _on_image_selected(self, img: ImageInfo):
        """图片选择事件"""
        self.preview_widget.show_image(img)

    def _on_select_all(self):
        """全选"""
        for i in range(self.image_list.count()):
            self.image_list.item(i).setSelected(True)

    def _on_clear_selection(self):
        """取消选择"""
        self.image_list.clearSelection()

    def closeEvent(self, event):
        """关闭事件"""
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(self.source_manager.close_all())
        event.accept()
