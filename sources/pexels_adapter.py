"""
Pexels API 适配器
Pexels 是一个免费的视频和图片素材平台
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


@register_adapter("pexels")
class PexelsAdapter(BaseSourceAdapter):
    """
    Pexels API 适配器
    需要注册获取 API Key: https://www.pexels.com/api/
    """

    BASE_URL = "https://api.pexels.com/v1"
    SEARCH_URL = f"{BASE_URL}/search"
    CURATED_URL = f"{BASE_URL}/curated"

    def __init__(self, api_key: Optional[str] = None):
        """
        :param api_key: Pexels API Key
                        如果不提供，需要设置环境变量 PEXELS_API_KEY
        """
        super().__init__()
        import os
        self.api_key = api_key or os.getenv("PEXELS_API_KEY")
        if not self.api_key:
            raise ValidationException(
                "Pexels API Key 未提供。"
                "请访问 https://www.pexels.com/api/ 注册获取 API Key，"
                "或设置环境变量 PEXELS_API_KEY"
            )
        self.headers = {
            "Authorization": self.api_key,
            "User-Agent": "PicFetch/1.0"
        }

    @property
    def source_name(self) -> str:
        return "Pexels"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索图片"""
        url = self.SEARCH_URL
        query_params = {
            "query": params.keywords,
            "per_page": params.per_page,
            "page": params.page,
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
            query_params["color"] = self._map_color(params.color)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    params=query_params
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise SearchException(
                            f"Pexels API 错误 (HTTP {response.status}): {error}"
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

    DownloadException

    def get_supported_resolutions(self) -> List[str]:
        return [
            "1920x1080 (FHD)",
            "2560x1440 (2K)",
            "3840x2160 (4K)",
            "自定义"
        ]

    def get_supported_formats(self) -> List[str]:
        return ["jpg", "png"]

    def get_supported_colors(self) -> List[str]:
        return [
            "red", "orange", "yellow", "green", "turquoise",
            "blue", "violet", "pink", "brown", "black", "gray",
            "white", "bright", "dark"
        ]

    async def validate(self) -> bool:
        """验证 API Key 是否有效"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/curated"
                async with session.get(
                    url,
                    headers=self.headers,
                    params={"per_page": 1}
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for photo in data.get("photos", []):
            src = photo.get("src", {})
            photographer = photo.get("photographer", "Unknown")
            photographer_url = photo.get("photographer_url", "")

            # 提取颜色信息
            avg_color = photo.get("avg_color", "")

            images.append(ImageInfo(
                url=src.get("original", src.get("large2x", "")),
                title=photo.get("alt", f"Photo by {photographer}"),
                author=photographer,
                width=photo.get("width", 0),
                height=photo.get("height", 0),
                format="jpg",
                source=self.source_name,
                preview_url=src.get("large"),
                download_url=src.get("original"),
                page_url=photo.get("url", photographer_url),
                tags=[avg_color] if avg_color else []
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
        """映射颜色参数到 Pexels API 支持的颜色"""
        color_map = {
            "红色": "red",
            "橙色": "orange",
            "黄色": "yellow",
            "绿色": "green",
            "青色": "turquoise",
            "蓝色": "blue",
            "紫色": "violet",
            "粉色": "pink",
            "棕色": "brown",
            "黑色": "black",
            "灰色": "gray",
            "白色": "white",
            "明亮": "red",  # Pexels 使用具体颜色
            "暗色": "black",
        }

        color_lower = color.lower()
        if color_lower.startswith("#"):
            return None

        # 先尝试中文映射
        for cn, en in color_map.items():
            if cn.lower() == color_lower or en.lower() == color_lower:
                return en

        return color_lower if color_lower in [
            "red", "orange", "yellow", "green", "turquoise",
            "blue", "violet", "pink", "brown", "black", "gray",
            "white"
        ] else None
