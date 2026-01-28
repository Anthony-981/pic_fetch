"""
图片爬取工具 - 主入口
"""
import sys
import os
from pathlib import Path

# 添加项目路径到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui.main_window import MainWindow


def setup_high_dpi():
    """设置高DPI支持"""
    # High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)


def setup_theme(app: QApplication):
    """设置应用主题样式"""
    app.setStyle("Fusion")

    # 深色主题样式
    style_sheet = """
    QMainWindow {
        background-color: #1e1e1e;
    }

    QWidget {
        background-color: #2d2d2d;
        color: #e0e0e0;
        font-family: "Microsoft YaHei UI", "Segoe UI", Arial;
        font-size: 10pt;
    }

    QGroupBox {
        border: 1px solid #444;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }

    QLineEdit {
        background-color: #3d3d3d;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 5px;
    }

    QLineEdit:focus {
        border: 1px solid #2196F3;
    }

    QComboBox {
        background-color: #3d3d3d;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 5px;
    }

    QComboBox::drop-down {
        border: none;
    }

    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid #e0e0e0;
        width: 0;
        height: 0;
    }

    QListWidget {
        background-color: #1e1e1e;
        border: 1px solid #444;
        border-radius: 3px;
        outline: none;
    }

    QListWidget::item {
        padding: 5px;
        border-radius: 3px;
    }

    QListWidget::item:selected {
        background-color: #2196F3;
    }

    QListWidget::item:hover {
        background-color: #3d3d3d;
    }

    QScrollBar:vertical {
        background-color: #2d2d2d;
        width: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical {
        background-color: #555;
        border-radius: 6px;
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #666;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QTabWidget::pane {
        border: 1px solid #444;
        background-color: #1e1e1e;
    }

    QTabBar::tab {
        background-color: #2d2d2d;
        border: 1px solid #444;
        border-bottom: none;
        padding: 8px 16px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background-color: #1e1e1e;
        border-bottom: 1px solid #1e1e1e;
    }

    QTabBar::tab:hover {
        background-color: #3d3d3d;
    }

    QStatusBar {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border-top: 1px solid #444;
    }

    QProgressBar {
        background-color: #3d3d3d;
        border: 1px solid #555;
        border-radius: 3px;
        text-align: center;
    }

    QProgressBar::chunk {
        background-color: #2196F3;
        border-radius: 2px;
    }

    QSpinBox {
        background-color: #3d3d3d;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 5px;
    }

    QSpinBox::up-button, QSpinBox::down-button {
        background-color: #444;
        border: none;
        width: 20px;
    }

    QLabel {
        color: #e0e0e0;
    }
    """
    app.setStyleSheet(style_sheet)


def check_env():
    """检查环境配置"""
    import sys

    # 设置 UTF-8 输出
    if sys.platform == "win32":
        import io
        if sys.stdout and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if sys.stderr and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # 检查 Unsplash API Key
    if not os.getenv("UNSPLASH_ACCESS_KEY"):
        print("=" * 60)
        print("[警告] 未设置 Unsplash API Key")
        print("=" * 60)
        print()
        print("要使用 Unsplash 图片源，你需要:")
        print("1. 访问 https://unsplash.com/developers")
        print("2. 注册并创建一个新应用")
        print("3. 获取 Access Key")
        print("4. 设置环境变量: UNSPLASH_ACCESS_KEY=你的密钥")
        print()
        print("或者在 .env.example 文件中配置 API Key。")
        print()
        print("Windows PowerShell:")
        print('  $env:UNSPLASH_ACCESS_KEY="your_key_here"')
        print()
        print("Windows CMD:")
        print('  set UNSPLASH_ACCESS_KEY=your_key_here')
        print()
        print("Linux/Mac:")
        print('  export UNSPLASH_ACCESS_KEY="your_key_here"')
        print()
        print("=" * 60)


def main():
    """主函数"""
    # 设置高DPI
    setup_high_dpi()

    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("图片爬取工具")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("PicFetch")

    # 设置主题
    setup_theme(app)

    # 检查环境
    check_env()

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
