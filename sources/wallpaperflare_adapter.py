"""
WallpaperFlare 壁纸爬虫适配器
WallpaperFlare.com 是一个免费的壁纸网站
"""
import aiohttp
from typing import List, Optional
from urllib.parse import urljoin, quote
import re
from bs4 import BeautifulSoup

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException,
    DownloadException
)
from core.source_factory import register_adapter


@register_adapter("wallpaperflare")
class WallpaperFlareAdapter(BaseSourceAdapter):
    """
    WallpaperFlare 壁纸爬虫适配器
    无需 API Key，直接爬取网页数据
    """

    BASE_URL = "https://www.wallpaperflare.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    @property
    def source_name(self) -> str:
        return "WallpaperFlare"

    @property
    def source_type(self) -> str:
        return "scraper"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索壁纸"""
        # 构建搜索 URL
        search_url = f"{self.SEARCH_URL}/{quote(params.keywords)}.html?"

        query_params = {"page": params.page}

        # 添加分辨率筛选
        if params.resolution:
            width, height = self._parse_resolution(params.resolution)
            query_params["width"] = width
            query_params["height"] = height
        elif params.min_width and params.min_height:
            query_params["width"] = params.min_width
            query_params["height"] = params.min_height

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{search_url}&{urlencode(query_params)}"
                async with session.get(
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise SearchException(
                            f"WallpaperFlare 错误 (HTTP {response.status})"
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
            "自定义"
        ]

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

        # 查找所有图片项
        photo_items = soup.select('ul.photo-list li')

        for item in photo_items:
            try:
                # 获取图片链接
                link_tag = item.select_one('a')
                if not link_tag:
                    continue

                page_url = urljoin(self.BASE_URL, link_tag.get('href', ''))
                img_id = page_url.split('/')[-1].replace('.html', '')

                # 获取缩略图
                img_tag = item.select_one('img')
                if not img_tag:
                    continue

                thumb_url = img_tag.get('data-src') or img_tag.get('src', '')
                title = img_tag.get('alt', 'Wallpaper')

                # 解析缩略图 URL 获取尺寸信息
                # WallpaperFlare 缩略图格式: https://.../w480/...
                # 我们需要访问详情页获取原图
                images.append(ImageInfo(
                    url=thumb_url,
                    title=title,
                    author="WallpaperFlare",
                    width=1920,
                    height=1080,
                    format="jpg",
                    source=self.source_name,
                    preview_url=thumb_url,
                    download_url=page_url,  # 临时设置为页面URL
                    page_url=page_url,
                    tags=[img_id]
                ))
            except Exception as e:
                print(f"解析图片项失败: {e}")
                continue

        # 获取原图下载链接
        await self._fetch_download_urls(images, session)

        return images

    async def _fetch_download_urls(self, images: List[ImageInfo], session) -> None:
        """获取原图下载链接"""
        for img in images:
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

                    # 查找下载链接
                    download_btn = soup.select_one('a.btn-download')
                    if download_btn:
                        download_url = download_btn.get('href', '')
                        if download_url and not download_url.startswith('http'):
                            download_url = urljoin(self.BASE_URL, download_url)
                        img.download_url = download_url
                        img.url = download_url

                    # 尝试获取更多信息
                    info_section = soup.select_one('.info')
                    if info_section:
                        # 解析分辨率
                        resolution_text = info_section.get_text()
                        res_match = re.search(r'(\d+)\s*[x×]\s*(\d+)', resolution_text)
                        if res_match:
                            img.width = int(res_match.group(1))
                            img.height = int(res_match.group(2))

            except Exception as e:
                print(f"获取下载链接失败 ({img.page_url}): {e}")
                continue

    def _parse_resolution(self, resolution: str) -> tuple[int, int]:
        """解析分辨率字符串"""
        try:
            resolution_map = {
                "fhd": (1920, 1080),
                "2k": (2560, 1440),
                "4k": (3840, 2160),
            }
            res_lower = resolution.lower().replace(" ", "").replace("(", "").replace(")", "")
            if res_lower in resolution_map:
                return resolution_map[res_lower]
            if "x" in res_lower:
                w, h = res_lower.split("x")
                return int(w), int(h)
        except (ValueError, AttributeError):
            pass
        return 1920, 1080
