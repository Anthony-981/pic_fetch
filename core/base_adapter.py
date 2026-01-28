"""
核心适配器基类模块
定义所有图片源适配器的接口和数据结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any
from enum import Enum


class ImageFormat(Enum):
    """支持的图片格式"""
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"


class ColorTone(Enum):
    """颜色色调选项"""
    BRIGHT = "bright"      # 明亮
    DARK = "dark"          # 暗色
    GRAYSCALE = "grayscale"  # 灰度
    BLACK_WHITE = "black_and_white"  # 黑白


class Resolution(Enum):
    """预设分辨率"""
    HD = "1920x1080"       # 1080p
    FHD = "1920x1080"      # Full HD
    QHD = "2560x1440"      # 2K
    UHD = "3840x2160"      # 4K
    FHD_PORTRAIT = "1080x1920"  # 竖屏
    MOBILE = "1080x2340"   # 手机
    TABLET = "2048x2732"   # 平板


@dataclass
class ImageInfo:
    """图片信息数据类"""
    url: str                    # 图片URL
    title: str                  # 图片标题/描述
    author: str                 # 作者
    width: int                  # 宽度
    height: int                 # 高度
    format: str                 # 格式 (jpg, png, webp)
    source: str                 # 来源名称
    preview_url: Optional[str] = None   # 预览图URL
    download_url: Optional[str] = None  # 下载URL（可能不同于url）
    file_size: Optional[int] = None     # 文件大小（字节）
    tags: List[str] = field(default_factory=list)  # 标签
    page_url: Optional[str] = None      # 原始页面URL

    @property
    def aspect_ratio(self) -> float:
        """宽高比"""
        if self.height > 0:
            return self.width / self.height
        return 1.0

    @property
    def is_horizontal(self) -> bool:
        """是否横向"""
        return self.width >= self.height

    @property
    def is_vertical(self) -> bool:
        """是否竖向"""
        return self.height > self.width

    @property
    def megapixels(self) -> float:
        """百万像素数"""
        return (self.width * self.height) / 1_000_000

    def get_resolution_string(self) -> str:
        """获取分辨率描述"""
        if self.width >= 3840:
            return f"{self.width}x{self.height} (4K)"
        elif self.width >= 2560:
            return f"{self.width}x{self.height} (2K)"
        elif self.width >= 1920:
            return f"{self.width}x{self.height} (FHD)"
        else:
            return f"{self.width}x{self.height}"


@dataclass
class SearchParams:
    """搜索参数"""
    keywords: str                           # 关键词
    resolution: Optional[str] = None        # 预设分辨率 (如 "1920x1080", "4K")
    min_width: Optional[int] = None         # 最小宽度
    max_width: Optional[int] = None         # 最大宽度
    min_height: Optional[int] = None        # 最小高度
    max_height: Optional[int] = None        # 最大高度
    color: Optional[str] = None             # 颜色色调 (bright, dark, 或十六进制)
    format: Optional[str] = None            # 图片格式 (jpg, png, webp)
    per_page: int = 20                      # 每页结果数
    page: int = 1                           # 页码

    def get_min_resolution(self) -> tuple[int, int]:
        """获取最小分辨率元组"""
        if self.resolution:
            try:
                w, h = self.resolution.lower().split("x")
                return int(w), int(h)
            except (ValueError, AttributeError):
                pass
        return self.min_width or 0, self.min_height or 0


@dataclass
class DownloadProgress:
    """下载进度信息"""
    image_info: ImageInfo
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, downloading, completed, failed
    error: Optional[str] = None
    save_path: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """下载进度百分比"""
        if self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return 0.0


class BaseSourceAdapter(ABC):
    """
    图片源适配器基类
    所有图片来源适配器都必须继承此类并实现抽象方法
    """

    def __init__(self):
        self._session = None

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        返回来源名称
        例如: "Unsplash", "Pexels", "百度图片"
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """
        返回来源类型
        'api' - 使用API接口
        'scraper' - 网页爬虫
        'search' - 搜索引擎
        """
        pass

    @abstractmethod
    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """
        搜索图片
        :param params: 搜索参数
        :return: 图片信息列表
        """
        pass

    @abstractmethod
    async def download(
        self,
        image_info: ImageInfo,
        save_path: str,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> str:
        """
        下载图片
        :param image_info: 图片信息
        :param save_path: 保存路径
        :param progress_callback: 进度回调函数
        :return: 实际保存的文件路径
        """
        pass

    def get_supported_resolutions(self) -> List[str]:
        """
        获取支持的分辨率列表
        子类可以重写此方法以返回特定支持的分辨率
        """
        return [r.value for r in Resolution]

    def get_supported_formats(self) -> List[str]:
        """
        获取支持的格式列表
        子类可以重写此方法以返回特定支持的格式
        """
        return [f.value for f in ImageFormat]

    def get_supported_colors(self) -> List[str]:
        """
        获取支持的颜色选项列表
        子类可以重写此方法
        """
        return [c.value for c in ColorTone]

    async def validate(self) -> bool:
        """
        验证适配器配置是否有效
        例如检查API密钥是否有效
        """
        return True

    async def close(self):
        """
        关闭适配器，释放资源
        例如关闭网络连接
        """
        pass

    async def __aenter__(self):
        await self.validate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class AdapterException(Exception):
    """适配器异常基类"""
    pass


class SearchException(AdapterException):
    """搜索异常"""
    pass


class DownloadException(AdapterException):
    """下载异常"""
    pass


class ValidationException(AdapterException):
    """验证异常"""
    pass
