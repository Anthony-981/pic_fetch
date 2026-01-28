"""
测试图片适配器
使用简单可靠的图片源，无需 API Key
"""
import aiohttp
from typing import List, Optional
from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    SearchException
)
from core.source_factory import register_adapter


@register_adapter("test")
class TestAdapter(BaseSourceAdapter):
    """
    测试适配器
    使用 Lorem Picsum 提供随机图片，无需 API Key
    """

    BASE_URL = "https://picsum.photos"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "测试图片源"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取随机图片"""
        images = []
        count = min(params.per_page, 30)

        # 直接生成图片 URL，不依赖 API
        for i in range(count):
            # 使用随机种子获取不同图片
            seed = f"{params.keywords}_{params.page}_{i}" if params.keywords else f"test_{params.page}_{i}"
            width = 1920
            height = 1080

            img_url = f"{self.BASE_URL}/{width}/{height}?random={i}"

            images.append(ImageInfo(
                url=img_url,
                title=f"随机图片 {i + 1}",
                author="Lorem Picsum",
                width=width,
                height=height,
                format="jpg",
                source=self.source_name,
                preview_url=img_url,
                download_url=img_url
            ))

        return images

    async def download(self, image_info: ImageInfo, save_path: str, progress_callback=None) -> str:
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

        except Exception as e:
            progress.status = "failed"
            progress.error = str(e)
            if progress_callback:
                progress_callback(progress)
            raise DownloadException(f"下载失败: {e}")

    def get_supported_resolutions(self) -> List[str]:
        return ["1920x1080 (FHD)"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        """验证连接"""
        return True
