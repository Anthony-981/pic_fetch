"""
Picsum Photos 适配器
Picsum 是一个免费的照片占位符服务
"""
import aiohttp
from typing import List, Optional
import random

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    SearchException
)
from core.source_factory import register_adapter


@register_adapter("picsum")
class PicsumAdapter(BaseSourceAdapter):
    """
    Picsum Photos 适配器
    无需 API Key，提供随机高质量照片
    """

    BASE_URL = "https://picsum.photos"
    API_URL = f"{BASE_URL}/v2/list"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "Picsum"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取随机照片列表"""
        query_params = {
            "page": params.page,
            "limit": min(params.per_page, 100),  # API 最大 100
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=self.headers,
                    params=query_params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise SearchException(
                            f"Picsum API 错误 (HTTP {response.status})"
                        )

                    data = await response.json()
                    return self._parse_response(data, params)

        except aiohttp.ClientError as e:
            raise SearchException(f"网络请求失败: {e}")

    async def download(
        self,
        image_info: ImageInfo,
        save_path: str,
        progress_callback: Optional[callable] = None
    ) -> str:
        """下载图片"""
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadProgress, DownloadException

        url = image_info.download_url or image_info.url

        try:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)

            progress = DownloadProgress(image_info=image_info, status="downloading")
            if progress_callback:
                progress_callback(progress)

            async with aiohttp.ClientSession() as session:
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
        return ["全部", "自定义"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        """验证连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=self.headers,
                    params={"page": 1, "limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_response(self, data: list, params: SearchParams) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for item in data:
            # 获取图片 ID
            img_id = item.get("id", "")
            author = item.get("author", "Unknown")
            width = item.get("width", 0)
            height = item.get("height", 0)

            # 构建下载 URL，根据分辨率调整
            download_url = self._build_download_url(img_id, width, height, params)

            images.append(ImageInfo(
                url=download_url,
                title=f"Photo by {author}",
                author=author,
                width=width,
                height=height,
                format="jpg",
                source=self.source_name,
                preview_url=f"{self.BASE_URL}/{img_id}/600/400",
                download_url=download_url,
                page_url=f"https://picsum.photos/id/{img_id}"
            ))

        return images

    def _build_download_url(self, img_id: str, width: int, height: int, params: SearchParams) -> str:
        """构建下载 URL"""
        # 根据用户选择的分辨率调整
        target_width, target_height = width, height

        if params.resolution:
            res_map = {
                "fhd": (1920, 1080),
                "2k": (2560, 1440),
                "4k": (3840, 2160),
                "8k": (7680, 4320),
            }
            res_lower = params.resolution.lower().replace(" ", "").replace("(", "").replace(")", "")
            if res_lower in res_map:
                target_width, target_height = res_map[res_lower]
            elif "x" in res_lower:
                w, h = res_lower.split("x")
                target_width, target_height = int(w), int(h)
        elif params.min_width and params.min_height:
            target_width = max(params.min_width, width)
            target_height = max(params.min_height, height)

        return f"{self.BASE_URL}/id/{img_id}/{target_width}/{target_height}"
