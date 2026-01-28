"""
主窗口模块
图片爬取工具的主界面
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QProgressBar,
    QLabel, QComboBox, QPushButton, QSpinBox, QLineEdit,
    QGroupBox, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QPixmap, QImage, QIcon, QAction
from pathlib import Path
from typing import List, Optional
import asyncio
import os

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


class SearchWorker(QThread):
    """搜索工作线程"""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, adapter, params: SearchParams):
        super().__init__()
        self.adapter = adapter
        self.params = params

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.adapter.search(self.params))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class ImageListWidget(QListWidget):
    """图片列表组件"""

    itemSelected = Signal(object)  # ImageInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setGridSize(QSize(220, 280))
        self.setIconSize(QSize(200, 200))
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(10)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.currentItemChanged.connect(self._on_selection_changed)

    def add_images(self, images: List[ImageInfo]):
        """添加图片到列表"""
        for img in images:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, img)
            item.setText(f"{img.title}\n{img.width}x{img.height}")
            self.addItem(item)

            # 异步加载预览图
            if img.preview_url:
                self._load_preview(item, img.preview_url)

    def _load_preview(self, item, url: str):
        """异步加载预览图"""
        loader = ImageLoader(url, item)
        loader.finished.connect(lambda pix: self._set_icon(item, pix))
        loader.start()

    def _set_icon(self, item, pixmap: Optional[QPixmap]):
        """设置图标"""
        if pixmap:
            item.setIcon(QIcon(pixmap))

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
        self.clear()


class ImageLoader(QThread):
    """图片加载线程"""
    finished = Signal(object)

    def __init__(self, url: str, item: QListWidgetItem):
        super().__init__()
        self.url = url
        self.item = item

    def run(self):
        import urllib.request
        try:
            req = urllib.request.Request(self.url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    self.finished.emit(pixmap)
        except Exception as e:
            print(f"加载图片失败: {e}")
            self.finished.emit(None)


class DownloadQueueWidget(QWidget):
    """下载队列组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 标题
        header = QLabel("下载队列")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # 列表
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)


class MainWindow(QMainWindow):
    """
    主窗口
    图片爬取工具的主界面
    """

    # 图片源映射
    SOURCE_MAP = {
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
        search_group = QGroupBox("搜索")
        search_layout = QVBoxLayout()

        # 关键词输入
        search_layout.addWidget(QLabel("关键词:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入搜索关键词...")
        search_layout.addWidget(self.keyword_input)

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
        search_layout.addWidget(self.search_btn)

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
        tab_widget = QTabWidget()

        # 图片预览标签页
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        self.result_count_label = QLabel("共 0 张图片")
        toolbar_layout.addWidget(self.result_count_label)
        toolbar_layout.addStretch()
        self.select_all_btn = QPushButton("全选")
        self.clear_selection_btn = QPushButton("取消选择")
        toolbar_layout.addWidget(self.select_all_btn)
        toolbar_layout.addWidget(self.clear_selection_btn)
        preview_layout.addLayout(toolbar_layout)

        # 图片列表
        self.image_list = ImageListWidget()
        preview_layout.addWidget(self.image_list)

        tab_widget.addTab(preview_widget, "图片预览")

        # 下载队列标签页
        self.download_queue = DownloadQueueWidget()
        tab_widget.addTab(self.download_queue, "下载队列")

        return tab_widget

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
        self.search_btn.clicked.connect(self._on_search)
        self.browse_btn.clicked.connect(self._on_browse_directory)
        self.download_btn.clicked.connect(self._on_download)
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.clear_selection_btn.clicked.connect(self._on_clear_selection)

    def _get_source_name(self) -> str:
        """获取选择的图片源内部名称"""
        display_name = self.source_combo.currentText()
        return self.SOURCE_MAP.get(display_name, "unsplash")

    def _on_search(self):
        """搜索按钮点击"""
        keywords = self.keyword_input.text().strip()
        if not keywords:
            QMessageBox.warning(self, "警告", "请输入搜索关键词")
            return

        self.search_btn.setEnabled(False)
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

        async def do_search():
            try:
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

                adapter = await self.source_manager.get_adapter(source_name, config=config)
                self.current_adapter = adapter

                params = SearchParams(
                    keywords=keywords,
                    per_page=30,
                    resolution=resolution,
                    format=format_filter.lower() if format_filter else None
                )

                results = await adapter.search(params)
                self.search_results = results

                # 在主线程更新UI
                QTimer.singleShot(0, lambda: self._update_search_results(results))

            except Exception as e:
                QTimer.singleShot(0, lambda: self._show_error(f"搜索失败: {e}"))
            finally:
                QTimer.singleShot(0, self._search_finished)

        # 在新事件循环中运行
        import threading
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(do_search())
            loop.close()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

    def _update_search_results(self, results: List[ImageInfo]):
        """更新搜索结果"""
        self.image_list.clear_images()
        self.image_list.add_images(results)
        self.result_count_label.setText(f"共 {len(results)} 张图片")
        self.status_label.setText(f"找到 {len(results)} 张图片")

    def _search_finished(self):
        """搜索完成"""
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("就绪")

    def _show_error(self, message: str):
        """显示错误"""
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

        # TODO: 实现下载逻辑
        QMessageBox.information(
            self,
            "提示",
            f"已选择 {len(images)} 张图片\n下载功能即将实现"
        )

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
