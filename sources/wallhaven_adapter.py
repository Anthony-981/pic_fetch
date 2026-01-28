"""
Wallhaven 壁纸爬虫适配器
Wallhaven.cc 是一个高质量的壁纸网站
"""
import aiohttp
from typing import List, Optional
from urllib.parse import urljoin, urlencode
import re

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException,
    DownloadException
)
from core.source_factory import register_adapter


@register_adapter("wallhaven")
class WallhavenAdapter(BaseSourceAdapter):
    """
    Wallhaven 壁纸爬虫适配器
    无需 API Key，直接爬取网页数据
    """

    BASE_URL = "https://wallhaven.cc"
    SEARCH_URL = f"{BASE_URL}/search"
    API_URL = f"{BASE_URL}/api/v1/search"

    def __init__(self, api_key: Optional[str] = None):
        """
        :param api_key: Wallhaven API Key (可选，有更高的请求限制)
        """
        super().__init__()
        self.api_key = api_key
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    @property
    def source_name(self) -> str:
        return "Wallhaven"

    @property
    def source_type(self) -> str:
        return "scraper"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索壁纸"""
        query_params = {
            "q": params.keywords,
            "page": params.page,
            "purity": "100",  # SFW (Safe For Work)
        }

        # 添加分辨率筛选
        if params.resolution:
            query_params["atleast"] = self._parse_resolution(params.resolution)
        elif params.min_width and params.min_height:
            query_params["atleast"] = f"{params.min_width}x{params.min_height}"

        # 添加宽高比筛选
        if params.min_width and params.min_height:
            ratio = params.min_width / params.min_height
            if ratio >= 1.5:
                query_params["ratios"] = "16x9"
            elif ratio <= 0.75:
                query_params["ratios"] = "9x16"

        # 添加颜色筛选
        if params.color:
            color = self._map_color(params.color)
            if color:
                query_params["color"] = color

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=self.headers,
                    params=query_params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise SearchException(
                            f"Wallhaven API 错误 (HTTP {response.status}): {error}"
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

            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        raise DownloadException(f"下载失败 (HTTP {response.status})")

                    total = int(response.headers.get('Content-Length', 0))
                    progress.total_bytes = total

                    downloaded = 0
                    async with aiofiles.open(save_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(16384):
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
            "7680x4320 (8K)",
            "自定义"
        ]

    def get_supported_formats(self) -> List[str]:
        return ["jpg", "png", "webp"]

    def get_supported_colors(self) -> List[str]:
        return [
            "red", "orange", "yellow", "green", "blue",
            "pink", "brown", "black", "white", "gray"
        ]

    async def validate(self) -> bool:
        """验证连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=self.headers,
                    params={"q": "nature", "page": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for wallpaper in data.get("data", []):
            # 获取图片信息
            path = wallpaper.get("path", "")
            thumbs = wallpaper.get("thumbs", {})

            # 获取分辨率
            dimension_x = wallpaper.get("dimension_x", 0)
            dimension_y = wallpaper.get("dimension_y", 0)

            # 获取分类和标签
            category = wallpaper.get("category", "")
            purity = wallpaper.get("purity", "sfw")
            tags = [tag.get("name", "") for tag in wallpaper.get("tags", [])]

            # 获取颜色
            colors = wallpaper.get("colors", [])

            images.append(ImageInfo(
                url=path,
                title=wallpaper.get("category", "Wallpaper"),
                author=wallpaper.get("uploader", {}).get("username", "Unknown"),
                width=dimension_x,
                height=dimension_y,
                format="jpg" if path.endswith(".jpg") else "png",
                source=self.source_name,
                preview_url=thumbs.get("large") or thumbs.get("original"),
                download_url=path,
                tags=tags[:10] if tags else [],
                page_url=f"{self.BASE_URL}/w/{wallpaper.get('id', '')}"
            ))

        return images

    def _parse_resolution(self, resolution: str) -> str:
        """解析分辨率字符串"""
        try:
            resolution_map = {
                "fhd": "1920x1080",
                "2k": "2560x1440",
                "4k": "3840x2160",
                "8k": "7680x4320",
            }
            res_lower = resolution.lower().replace(" ", "").replace("(", "").replace(")", "")
            if res_lower in resolution_map:
                return resolution_map[res_lower]
            if "x" in res_lower:
                return res_lower
        except (ValueError, AttributeError):
            pass
        return "1920x1080"

    def _map_color(self, color: str) -> Optional[str]:
        """映射颜色参数到 Wallhaven API 支持的颜色"""
        color_map = {
            "红色": "red",
            "橙色": "orange",
            "黄色": "yellow",
            "绿色": "green",
            "青色": "teal",
            "蓝色": "blue",
            "紫色": "purple",
            "粉色": "pink",
            "棕色": "brown",
            "黑色": "black",
            "白色": "white",
            "灰色": "gray",
            "明亮": "white",
            "暗色": "black",
        }

        color_lower = color.lower()

        # 中文映射
        for cn, en in color_map.items():
            if cn.lower() == color_lower or en.lower() == color_lower:
                return en

        # 检查是否是支持的颜色
        supported = ["red", "orange", "yellow", "green", "blue",
                     "pink", "brown", "black", "white", "gray"]
        return color_lower if color_lower in supported else None
