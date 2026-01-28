"""
Bing 每日壁纸 API 适配器
获取 Bing 每日壁纸，支持历史壁纸
"""
import aiohttp
from typing import List, Optional
from datetime import datetime, timedelta
import re

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException
)
from core.source_factory import register_adapter


@register_adapter("bing_daily")
class BingDailyAdapter(BaseSourceAdapter):
    """
    Bing 每日壁纸 API 适配器
    无需 API Key，使用 Bing 官方接口
    """

    BASE_URL = "https://www.bing.com"
    API_URL = f"{BASE_URL}/HPImageArchive.aspx"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "Bing每日壁纸"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取每日壁纸"""
        # 获取最近几天的壁纸（最多8天）
        days = min(8, 30)  # API 限制最多 8 张
        idx = 0  # 0=今天, 1=昨天, ...

        query_params = {
            "format": "js",
            "idx": idx,
            "n": days,
            "mkt": "zh-CN",  # 中国市场
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
                            f"Bing API 错误 (HTTP {response.status})"
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
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadException

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
        return ["1920x1080 (FHD)", "UHD (4K)"]

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
                    params={"format": "js", "idx": 0, "n": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for item in data.get("images", []):
            # 获取图片基本信息
            urlbase = item.get("urlbase", "")
            startdate = item.get("startdate", "")
            enddate = item.get("enddate", "")
            copyright_text = item.get("copyright", "")
            copyright_link = item.get("copyrightlink", "")

            # 构建下载 URL
            # Bing 提供多种分辨率，默认使用 1920x1080
            download_url = f"{self.BASE_URL}{urlbase}_1920x1080.jpg"
            uhd_url = f"{self.BASE_URL}{urlbase}_UHD.jpg"

            # 解析日期
            try:
                date_str = f"{startdate[:4]}-{startdate[4:6]}-{startdate[6:8]}"
            except:
                date_str = startdate

            images.append(ImageInfo(
                url=download_url,
                title=f"{copyright_text} ({date_str})",
                author="Bing",
                width=1920,
                height=1080,
                format="jpg",
                source=self.source_name,
                preview_url=f"{self.BASE_URL}{urlbase}_800x480.jpg",
                download_url=download_url,
                page_url=copyright_link,
                tags=["bing", "daily", "wallpaper", date_str]
            ))

        return images
