"""
中文壁纸 API 适配器
支持：搏天API、小歪API、360壁纸API、姬长信API
"""
import aiohttp
from typing import List, Optional
import random

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    SearchParams,
    DownloadProgress,
    SearchException
)
from core.source_factory import register_adapter


# ==================== 搏天 API ====================

@register_adapter("botian")
class BotianAdapter(BaseSourceAdapter):
    """
    搏天 API 适配器
    免费 JSON API 壁纸接口
    """

    API_URL = "https://api.btstu.cn/doc.php"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "搏天壁纸"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取随机壁纸"""
        images = []
        count = min(params.per_page, 30)

        for _ in range(count):
            # 搏天 API 提供多种类型
            api_types = [
                "https://api.btstu.cn/sjbz/api.php?format=json",
                "https://api.btstu.cn/tx/api.php?format=json",
            ]

            url = random.choice(api_types)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            data = await response.json()
                            img_url = data.get("imgurl") or data.get("url")

                            if img_url:
                                images.append(ImageInfo(
                                    url=img_url,
                                    title=f"随机壁纸 {len(images) + 1}",
                                    author="搏天API",
                                    width=1920,
                                    height=1080,
                                    format="jpg",
                                    source=self.source_name,
                                    preview_url=img_url,
                                    download_url=img_url
                                ))
            except Exception:
                continue

        return images

    async def download(self, image_info: ImageInfo, save_path: str, progress_callback: Optional[callable] = None) -> str:
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadException

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        progress = DownloadProgress(image_info=image_info, status="downloading")
        if progress_callback:
            progress_callback(progress)

        async with aiohttp.ClientSession() as session:
            async with session.get(image_info.url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise DownloadException(f"下载失败 (HTTP {response.status})")

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
                return save_path

    def get_supported_resolutions(self) -> List[str]:
        return ["1920x1080"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        return True


# ==================== 小歪 API ====================

@register_adapter("xiaowai")
class XiaowaiAdapter(BaseSourceAdapter):
    """
    小歪 API 适配器
    免费 JSON API 壁纸接口
    """

    BASE_URL = "https://t.alcy.cc"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "小歪壁纸"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取随机壁纸"""
        images = []
        count = min(params.per_page, 30)

        # 小歪 API 提供多种类型
        api_endpoints = [
            "/moyu",    # 摸鱼
            "/yc",      # 二次元
            "/dome",    # 风景
            "/bz",      # 壁纸
        ]

        for i in range(count):
            endpoint = random.choice(api_endpoints)
            url = f"{self.BASE_URL}{endpoint}?json={i}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            # 小歪 API 直接返回图片
                            img_url = str(response.url)

                            images.append(ImageInfo(
                                url=img_url,
                                title=f"随机壁纸 {i + 1}",
                                author="小歪API",
                                width=1920,
                                height=1080,
                                format="jpg",
                                source=self.source_name,
                                preview_url=img_url,
                                download_url=img_url
                            ))
            except Exception:
                continue

        return images

    async def download(self, image_info: ImageInfo, save_path: str, progress_callback: Optional[callable] = None) -> str:
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadException

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        progress = DownloadProgress(image_info=image_info, status="downloading")
        if progress_callback:
            progress_callback(progress)

        async with aiohttp.ClientSession() as session:
            async with session.get(image_info.url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise DownloadException(f"下载失败 (HTTP {response.status})")

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
                return save_path

    def get_supported_resolutions(self) -> List[str]:
        return ["1920x1080"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        return True


# ==================== 360 壁纸 API ====================

@register_adapter("wallpaper360")
class Wallpaper360Adapter(BaseSourceAdapter):
    """
    360 壁纸 API 适配器
    360 壁纸网站的 JSON 接口
    """

    BASE_URL = "http://wallpaper.apc.360.cn"
    API_URL = f"{BASE_URL}/index.php"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "360壁纸"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索壁纸"""
        categories = {
            "风景": "1002",
            "美图": "1001",
            "动漫": "1006",
            "萌宠": "1005",
            "明星": "1004",
            "游戏": "1007",
            "汽车": "1003",
            "影视": "1008",
        }

        # 根据关键词选择分类，默认风景
        cid = "1002"
        for keyword, cat_id in categories.items():
            if keyword in params.keywords:
                cid = cat_id
                break

        query_params = {
            "c": "WallPaper",
            "a": "getAppsByCategory",
            "cid": cid,
            "start": (params.page - 1) * params.per_page,
            "count": params.per_page,
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
                        raise SearchException(f"360 API 错误 (HTTP {response.status})")

                    data = await response.json()
                    return self._parse_response(data)

        except aiohttp.ClientError as e:
            raise SearchException(f"网络请求失败: {e}")

    async def download(self, image_info: ImageInfo, save_path: str, progress_callback: Optional[callable] = None) -> str:
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadException

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        progress = DownloadProgress(image_info=image_info, status="downloading")
        if progress_callback:
            progress_callback(progress)

        async with aiohttp.ClientSession() as session:
            async with session.get(image_info.url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise DownloadException(f"下载失败 (HTTP {response.status})")

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
                return save_path

    def get_supported_resolutions(self) -> List[str]:
        return ["1920x1080"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        return True

    def _parse_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for item in data.get("data", []):
            # 获取图片 URL 列表
            url_obj = item.get("url", [])
            if isinstance(url_obj, list) and len(url_obj) > 0:
                # 选择最高分辨率
                img_url = url_obj[-1] if isinstance(url_obj[-1], str) else url_obj[0]

                images.append(ImageInfo(
                    url=img_url,
                    title=item.get("utag", "360壁纸"),
                    author="360壁纸",
                    width=1920,
                    height=1080,
                    format="jpg",
                    source=self.source_name,
                    preview_url=img_url,
                    download_url=img_url,
                    tags=item.get("tag", "").split(",") if item.get("tag") else []
                ))

        return images


# ==================== 姬长信 API ====================

@register_adapter("jichangxin")
class JichangxinAdapter(BaseSourceAdapter):
    """
    姬长信 API 适配器
    免费 JSON API 壁纸接口
    """

    BASE_URL = "https://api.oick.cn"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @property
    def source_name(self) -> str:
        return "姬长信壁纸"

    @property
    def source_type(self) -> str:
        return "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """获取随机壁纸"""
        images = []
        count = min(params.per_page, 30)

        # 姬长信 API 提供多种类型
        api_endpoints = [
            "/random/api.php",
            "/sdg/api.php",
        ]

        for i in range(count):
            endpoint = random.choice(api_endpoints)
            url = f"{self.BASE_URL}{endpoint}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            data = await response.json()
                            img_url = data.get("imgurl") or data.get("url")

                            if img_url:
                                images.append(ImageInfo(
                                    url=img_url,
                                    title=f"随机壁纸 {i + 1}",
                                    author="姬长信API",
                                    width=1920,
                                    height=1080,
                                    format="jpg",
                                    source=self.source_name,
                                    preview_url=img_url,
                                    download_url=img_url
                                ))
            except Exception:
                continue

        return images

    async def download(self, image_info: ImageInfo, save_path: str, progress_callback: Optional[callable] = None) -> str:
        import aiofiles
        from pathlib import Path
        from core.base_adapter import DownloadException

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        progress = DownloadProgress(image_info=image_info, status="downloading")
        if progress_callback:
            progress_callback(progress)

        async with aiohttp.ClientSession() as session:
            async with session.get(image_info.url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise DownloadException(f"下载失败 (HTTP {response.status})")

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
                return save_path

    def get_supported_resolutions(self) -> List[str]:
        return ["1920x1080"]

    def get_supported_formats(self) -> List[str]:
        return ["jpg"]

    def get_supported_colors(self) -> List[str]:
        return []

    async def validate(self) -> bool:
        return True
