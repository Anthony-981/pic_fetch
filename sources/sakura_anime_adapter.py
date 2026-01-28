"""
樱花动漫壁纸适配器
从樱花动漫网站爬取二次元壁纸
"""
import aiohttp
from typing import List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import re

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException
)
from core.source_factory import register_adapter


@register_adapter("sakura_anime")
class SakuraAnimeAdapter(BaseSourceAdapter):
    """
    樱花动漫壁纸适配器
    爬取二次元/动漫壁纸
    """

    BASE_URL = "https://www.yhdmp.com"
    SEARCH_URL = f"{BASE_URL}/wallpaper"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.BASE_URL,
        }

    @property
    def source_name(self) -> str:
        return "樱花动漫"

    @property
    def source_type(self) -> str:
        return "scraper"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索动漫壁纸"""
        # 构建搜索 URL
        search_url = f"{self.SEARCH_URL}/"

        # 添加搜索关键词
        if params.keywords:
            search_url = f"{self.SEARCH_URL}/search/{params.keywords}"

        # 添加分页
        if params.page > 1:
            search_url += f"/page/{params.page}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise SearchException(
                            f"樱花动漫 错误 (HTTP {response.status})"
                        )

                    html = await response.text()
                    return self._parse_search_page(html, session)

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
        return ["1920x1080", "2560x1440", "3840x2160"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg", "png"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        """验证连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.BASE_URL,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _parse_search_page(self, html: str, session) -> List[ImageInfo]:
        """解析搜索结果页面"""
        soup = BeautifulSoup(html, 'lxml')
        images = []

        # 查找壁纸列表项
        wallpaper_items = soup.select('.wallpaper-item') or soup.select('.pic-list li')

        for item in wallpaper_items:
            try:
                # 获取链接和标题
                link = item.select_one('a')
                if not link:
                    continue

                page_url = urljoin(self.BASE_URL, link.get('href', ''))

                # 获取缩略图
                img = item.select_one('img')
                if not img:
                    continue

                thumb_url = img.get('data-src') or img.get('src', '')
                title = img.get('alt', '动漫壁纸')

                # 默认尺寸
                images.append(ImageInfo(
                    url=thumb_url,
                    title=title,
                    author="樱花动漫",
                    width=1920,
                    height=1080,
                    format="jpg" if thumb_url.endswith('.jpg') else "png",
                    source=self.source_name,
                    preview_url=thumb_url,
                    download_url=page_url,  # 需要访问详情页获取原图
                    page_url=page_url
                ))
            except Exception as e:
                print(f"解析壁纸项失败: {e}")
                continue

        # 尝试获取原图下载链接
        await self._fetch_download_urls(images, session)

        return images

    async def _fetch_download_urls(self, images: List[ImageInfo], session) -> None:
        """获取原图下载链接"""
        for img in images[:10]:  # 限制并发请求数量
            try:
                async with session.get(
                    img.page_url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        continue

                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')

                    # 查找原图链接
                    download_img = soup.select_one('.wallpaper-detail img')
                    if download_img:
                        download_url = download_img.get('src', '')
                        if download_url and not download_url.startswith('http'):
                            download_url = urljoin(self.BASE_URL, download_url)
                        img.download_url = download_url
                        img.url = download_url

            except Exception:
                continue
