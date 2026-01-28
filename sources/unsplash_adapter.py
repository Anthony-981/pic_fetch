"""
Unsplash API 适配器
Unsplash 是一个高质量免费图片平台
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


@register_adapter("unsplash")
class UnsplashAdapter(BaseSourceAdapter):
    """
    Unsplash API 适配器
    需要注册获取 Access Key: https://unsplash.com/developers
    """

    # API 端点
    BASE_URL = "https://api.unsplash.com"
    SEARCH_URL = f"{BASE_URL}/search/photos"
    PHOTO_URL = f"{BASE_URL}/photos"

    # 支持的尺寸
    SIZES = {
        "thumb": (200, 200),
        "small": (400, 300),
        "regular": (1080, 720),
        "full": (1920, 1280),
        "raw": (0, 0),  # 原始尺寸
    }

    def __init__(self, access_key: Optional[str] = None):
        """
        :param access_key: Unsplash API Access Key
                          如果不提供，需要设置环境变量 UNSPLASH_ACCESS_KEY
        """
        super().__init__()
        import os
        self.access_key = access_key or os.getenv("UNSPLASH_ACCESS_KEY")
        if not self.access_key:
            raise ValidationException(
                "Unsplash API Key 未提供。"
                "请访问 https://unsplash.com/developers 注册获取 Access Key，"
                "或设置环境变量 UNSPLASH_ACCESS_KEY"
            )
        self.headers = {
            "Authorization": f"Client-ID {self.access_key}",
            "Accept-Version": "v1"
        }

    @property
    def source_name(self) -> str:
        return "Unsplash"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """
        搜索图片
        :param params: 搜索参数
        :return: 图片信息列表
        """
        url = self.SEARCH_URL
        query_params = {
            "query": params.keywords,
            "page": params.page,
            "per_page": params.per_page,
        }

        # 添加筛选参数
        if params.orientation:
            query_params["orientation"] = params.orientation
        if params.color:
            query_params["color"] = self._map_color(params.color)

        # 分辨率筛选
        if params.min_width or params.min_height:
            query_params["width"] = params.min_width or 1920
            query_params["height"] = params.min_height or 1080

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
                            f"Unsplash API 错误 (HTTP {response.status}): {error}"
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
        """
        下载图片
        :param image_info: 图片信息
        :param save_path: 保存路径
        :param progress_callback: 进度回调
        :return: 实际保存路径
        """
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
                        raise DownloadException(
                            f"下载失败 (HTTP {response.status})"
                        )

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
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return [
            "black_and_white",
            "black",
            "white",
            "yellow",
            "orange",
            "red",
            "purple",
            "magenta",
            "green",
            "teal",
            "blue"
        ]

    async def validate(self) -> bool:
        """
        验证 API Key 是否有效
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/users"
                async with session.get(
                    url,
                    headers=self.headers,
                    params={"username": "unsplash"}
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """
        解析 API 响应
        :param data: API 返回的 JSON 数据
        :return: 图片信息列表
        """
        images = []

        for result in data.get("results", []):
            urls = result.get("urls", {})
            user = result.get("user", {})

            # 获取原始尺寸
            width = result.get("width", 0)
            height = result.get("height", 0)

            # 构建标签
            tags = []
            for tag in result.get("tags", []):
                tag_title = tag.get("title", "")
                if tag_title:
                    tags.append(tag_title)

            images.append(ImageInfo(
                url=urls.get("full", urls.get("regular", "")),
                title=result.get("description")
                    or result.get("alt_description")
                    or f"Photo by {user.get('name', 'Unknown')}",
                author=user.get("name", "Unknown"),
                width=width,
                height=height,
                format="jpg",
                source=self.source_name,
                preview_url=urls.get("regular"),
                download_url=urls.get("full"),
                tags=tags,
                page_url=result.get("links", {}).get("html")
            ))

        return images

    def _map_color(self, color: str) -> Optional[str]:
        """
        映射颜色参数到 Unsplash API 支持的颜色
        :param color: 用户输入的颜色
        :return: Unsplash API 颜色值
        """
        color_map = {
            "black": "black",
            "white": "white",
            "yellow": "yellow",
            "orange": "orange",
            "red": "red",
            "purple": "purple",
            "magenta": "purple",
            "green": "green",
            "teal": "teal",
            "blue": "blue",
            "gray": "black_and_white",
            "grey": "black_and_white",
            "grayscale": "black_and_white",
            "bright": None,
            "dark": None,
        }

        color_lower = color.lower()
        if color_lower.startswith("#"):
            # 十六进制颜色，Unsplash 不支持，返回 None
            return None

        return color_map.get(color_lower, color_lower)
