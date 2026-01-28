"""
Pixabay API 适配器
Pixabay 是一个免费的高质量图片、矢量图和插画素材平台
"""
import aiohttp
from typing import List, Optional
from datetime import datetime

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException,
    DownloadException,
    ValidationException
)
from core.source_factory import register_adapter


@register_adapter("pixabay")
class PixabayAdapter(BaseSourceAdapter):
    """
    Pixabay API 适配器
    需要注册获取 API Key: https://pixabay.com/api/docs/
    """

    BASE_URL = "https://pixabay.com/api/"

    def __init__(self, api_key: Optional[str] = None):
        """
        :param api_key: Pixabay API Key
                        如果不提供，需要设置环境变量 PIXABAY_API_KEY
        """
        super().__init__()
        import os
        self.api_key = api_key or os.getenv("PIXABAY_API_KEY")
        if not self.api_key:
            raise ValidationException(
                "Pixabay API Key 未提供。"
                "请访问 https://pixabay.com/api/docs/ 注册获取 API Key，"
                "或设置环境变量 PIXABAY_API_KEY"
            )
        self.headers = {
            "User-Agent": "PicFetch/1.0"
        }

    @property
    def source_name(self) -> str:
        return "Pixabay"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索图片"""
        query_params = {
            "key": self.api_key,
            "q": params.keywords,
            "per_page": min(params.per_page, 200),  # Pixabay 最大 200
            "page": params.page,
            "image_type": "photo",  # 只要照片
            "safesearch": "true",  # 安全搜索
        }

        # 添加筛选参数
        if params.min_width:
            query_params["min_width"] = params.min_width
        if params.min_height:
            query_params["min_height"] = params.min_height

        # 分辨率映射
        if params.resolution:
            width, height = self._parse_resolution(params.resolution)
            query_params["min_width"] = width
            query_params["min_height"] = height

        # 颜色筛选
        if params.color:
            color = self._map_color(params.color)
            if color:
                query_params["colors"] = color

        # 格式筛选
        if params.format:
            format_map = {"jpg": "photo", "png": "photo", "webp": "illustration"}
            if params.format in format_map:
                query_params["image_type"] = format_map[params.format]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.BASE_URL,
                    headers=self.headers,
                    params=query_params
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise SearchException(
                            f"Pixabay API 错误 (HTTP {response.status}): {error}"
                        )

                    data = await response.json()
                    return self._parse_response(data)

        except aiohttp.ClientError as e:
            raise SearchException(f"网络请求失败: {e}")

    async def download(
        self,
        image_info: ImageInfo,
        save_path: str,
        progress_callback: Optional[callable] = None
    ) -> str:
        """下载图片"""
        url = image_info.download_url or image_info.url

        try:
            import aiofiles
            from pathlib import Path

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)

            progress = DownloadProgress(image_info=image_info, status="downloading")
            if progress_callback:
                progress_callback(progress)

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise DownloadException(f"下载失败 (HTTP {response.status})")

                    total = int(response.headers.get('Content-Length', 0))
                    progress.total_bytes = total

                    downloaded = 0
                    async with aiofiles.open(save_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            progress.downloaded_bytes = downloaded
                            if progress_callback:
                                progress_callback(progress)

                    progress.status = "completed"
                    progress.save_path = save_path
                    if progress_callback:
                        progress_callback(progress)

                    return save_path

        except aiohttp.ClientError as e:
            progress.status = "failed"
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            raise DownloadException(f"下载失败: {e}")

    def get_supported_resolutions(self) -> List[str]:
        return [
            "1920x1080 (FHD)",
            "2560x1440 (2K)",
            "3840x2160 (4K)",
            "自定义"
        ]

    def get_supported_formats(self) -> List[str]:
        return ["jpg", "png", "webp"]

    def get_supported_colors(self) -> List[str]:
        return [
            "grayscale", "transparent", "red", "orange", "yellow",
            "green", "turquoise", "blue", "lilac", "white", "black", "brown"
        ]

    async def validate(self) -> bool:
        """验证 API Key 是否有效"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.BASE_URL,
                    headers=self.headers,
                    params={"key": self.api_key, "per_page": 3}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("totalHits", 0) >= 0
                    return False
        except Exception:
            return False

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for hit in data.get("hits", []):
            # 获取不同尺寸的URL
            webformat_url = hit.get("webformatURL", "")
            large_url = hit.get("largeImageURL", "")
            full_hd_url = hit.get("fullHDURL", "")
            image_url = hit.get("imageURL", "")

            # 选择最佳下载URL
            download_url = full_hd_url or large_url or webformat_url or image_url

            # 获取标签
            tags = hit.get("tags", "").split(", ")

            images.append(ImageInfo(
                url=download_url,
                title=hit.get("tags", f"Image by {hit.get('user', 'Unknown')}"),
                author=hit.get("user", "Unknown"),
                width=hit.get("imageWidth", 0),
                height=hit.get("imageHeight", 0),
                format="jpg",
                source=self.source_name,
                preview_url=webformat_url,
                download_url=download_url,
                tags=tags,
                page_url=hit.get("pageURL")
            ))

        return images

    def _parse_resolution(self, resolution: str) -> tuple[int, int]:
        """解析分辨率字符串"""
        try:
            resolution_map = {
                "fhd": (1920, 1080),
                "2k": (2560, 1440),
                "4k": (3840, 2160),
            }
            res_lower = resolution.lower().replace(" ", "")
            if res_lower in resolution_map:
                return resolution_map[res_lower]
            if "x" in res_lower:
                w, h = res_lower.split("x")
                return int(w), int(h)
        except (ValueError, AttributeError):
            pass
        return 1920, 1080

    def _map_color(self, color: str) -> Optional[str]:
        """映射颜色参数到 Pixabay API 支持的颜色"""
        color_map = {
            "红色": "red",
            "橙色": "orange",
            "黄色": "yellow",
            "绿色": "green",
            "青色": "turquoise",
            "蓝色": "blue",
            "紫色": "lilac",
            "白色": "white",
            "黑色": "black",
            "棕色": "brown",
            "灰色": "grayscale",
            "透明": "transparent",
            "明亮": "white",
            "暗色": "black",
        }

        color_lower = color.lower()

        # 中文映射
        for cn, en in color_map.items():
            if cn.lower() == color_lower or en.lower() == color_lower:
                return en

        # 检查是否是支持的颜色
        supported = ["grayscale", "transparent", "red", "orange", "yellow",
                     "green", "turquoise", "blue", "lilac", "white", "black", "brown"]
        return color_lower if color_lower in supported else None
