"""
配置文件模块
"""
import os
from pathlib import Path
from typing import Optional


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 默认保存目录
DEFAULT_SAVE_DIR = Path.home() / "Pictures" / "pic_fetch"

# API 密钥配置
API_KEYS = {
    "unsplash": os.getenv("UNSPLASH_ACCESS_KEY"),
    "pexels": os.getenv("PEXELS_API_KEY"),
    "pixabay": os.getenv("PIXABAY_API_KEY"),
}

# 下载配置
DOWNLOAD_CONFIG = {
    "max_concurrent": 5,        # 最大并发下载数
    "timeout": 30,              # 请求超时（秒）
    "chunk_size": 8192,         # 下载块大小（字节）
    "max_retries": 3,           # 最大重试次数
}

# GUI 配置
GUI_CONFIG = {
    "window_width": 1400,
    "window_height": 900,
    "image_preview_size": 200,
    "grid_spacing": 10,
}

# 支持的图片来源
SUPPORTED_SOURCES = [
    "unsplash",
    # "pexels",
    # "pixabay",
    # "wallhaven",
    # "baidu",
    # "google",
    # "bing",
]


def get_api_key(source: str) -> Optional[str]:
    """获取指定来源的 API Key"""
    return API_KEYS.get(source)


def get_save_dir() -> Path:
    """获取保存目录"""
    save_dir = os.getenv("PIC_FETCH_SAVE_DIR")
    if save_dir:
        return Path(save_dir)
    return DEFAULT_SAVE_DIR


def ensure_save_dir() -> Path:
    """确保保存目录存在"""
    save_dir = get_save_dir()
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir
