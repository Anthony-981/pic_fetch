"""
Bing 图片搜索适配器
使用 Bing Images API 搜索图片
"""
import aiohttp
import json
from typing import List, Optional
from urllib.parse import quote, urlencode

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


@register_adapter("bing")
class BingAdapter(BaseSourceAdapter):
    """
    Bing 图片搜索适配器
    需要注册获取 Azure Bing Search API Key: https://www.microsoft.com/cognitive-services
    或者使用网页爬虫方式（无需 API Key）
    """

    # Bing Images API v7
    API_BASE_URL = "https://api.cognitive.microsoft.com/bing/v7.0/images/search"

    # 网页爬虫方式
    WEB_SEARCH_URL = "https://www.bing.com/images/async"

    def __init__(self, api_key: Optional[str] = None):
        """
        :param api_key: Bing Search API Key (可选)
                        如果不提供，将使用网页爬虫方式
        """
        super().__init__()
        self.api_key = api_key
        self.api_headers = {
            "Ocp-Apim-Subscription-Key": api_key
        } if api_key else {}

        self.web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.bing.com/images",
        }

    @property
    def source_name(self) -> str:
        return "Bing图片"

    @property
    def source_type(self) -> str:
        return "search" if not self.api_key else "api"

    async def search(self, params: SearchParams) -> List[ImageInfo]:
        """搜索图片"""
        if self.api_key:
            return await self._search_api(params)
        else:
            return await self._search_web(params)

    async def _search_api(self, params: SearchParams) -> List[ImageInfo]:
        """使用 Bing API 搜索"""
        query_params = {
            "q": params.keywords,
            "count": min(params.per_page, 150),  # API 最大 150
            "offset": (params.page - 1) * params.per_page,
            "safeSearch": "Moderate",
            "imageType": "Photo",
        }

        # 添加尺寸筛选
        if params.resolution:
            query_params["size"] = self._map_resolution(params.resolution)
        elif params.min_width and params.min_height:
            if params.min_width >= 3840:
                query_params["size"] = "Wallpaper"
            elif params.min_width >= 1920:
                query_params["size"] = "Large"

        # 添加颜色筛选
        if params.color:
            query_params["color"] = self._map_color(params.color)

        # 添加格式筛选
        if params.format:
            format_map = {"jpg": "Jpg", "png": "Png", "gif": "Gif", "webp": "Transparent"}
            if params.format in format_map:
                query_params["imageType"] = format_map[params.format]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_BASE_URL,
                    headers=self.api_headers,
                    params=query_params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise SearchException(
                            f"Bing API 错误 (HTTP {response.status}): {error}"
                        )

                    data = await response.json()
                    return self._parse_api_response(data)

        except aiohttp.ClientError as e:
            raise SearchException(f"网络请求失败: {e}")

    async def _search_web(self, params: SearchParams) -> List[ImageInfo]:
        """使用网页爬虫搜索"""
        query_params = {
            "q": params.keywords,
            "count": min(params.per_page, 35),  # Bing 网页每页约 35 张
            "first": (params.page - 1) * 35 + 1,
            "mmasync": "1",
            "qft": "",  # 筛选条件
        }

        # 构建筛选条件
        qft = []
        if params.resolution:
            qft.append(self._build_resolution_filter(params.resolution))
        if params.color:
            qft.append(self._build_color_filter(params.color))
        if params.format:
            qft.append(self._build_format_filter(params.format))

        if qft:
            query_params["qft"] = "+".join(qft)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.WEB_SEARCH_URL,
                    headers=self.web_headers,
                    params=query_params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise SearchException(
                            f"Bing 网页请求失败 (HTTP {response.status})"
                        )

                    html = await response.text()
                    return self._parse_web_response(html)

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

            headers = {"User-Agent": self.web_headers["User-Agent"]}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
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
            "全部",
            "1920x1080 (FHD)",
            "2560x1440 (2K)",
            "3840x2160 (4K)",
            "大于 4K",
        ]

    def get_supported_formats(self) -> List[str]:
        return ["jpg", "png", "gif", "webp", "全部"]

    def get_supported_colors(self) -> List[str]:
        return [
            "全部",
            "黑白",
            "红色",
            "橙色",
            "黄色",
            "绿色",
            "青色",
            "蓝色",
            "紫色",
            "粉色",
            "棕色",
            "黑色",
            "白色",
        ]

    async def validate(self) -> bool:
        """验证配置"""
        try:
            async with aiohttp.ClientSession() as session:
                # 测试网页方式
                async with session.get(
                    "https://www.bing.com/images",
                    headers=self.web_headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _parse_api_response(self, data: dict) -> List[ImageInfo]:
        """解析 API 响应"""
        images = []

        for value in data.get("value", []):
            # 获取最佳尺寸的图片
            content_url = value.get("contentUrl", "")
            thumbnail_url = value.get("thumbnailUrl", "")

            # 解析尺寸
            width = value.get("width", 0)
            height = value.get("height", 0)

            images.append(ImageInfo(
                url=content_url,
                title=value.get("name", "Bing Image"),
                author=value.get("hostPageDisplayUrl", "Unknown"),
                width=width,
                height=height,
                format=self._extract_format(content_url),
                source=self.source_name,
                preview_url=thumbnail_url,
                download_url=content_url,
                page_url=value.get("hostPageUrl")
            ))

        return images

    def _parse_web_response(self, html: str) -> List[ImageInfo]:
        """解析网页响应"""
        images = []

        # Bing 的异步搜索返回 JavaScript 代码
        # 查找包含图片数据的 JSON 对象
        try:
            # 查找 "mediaType":"Image" 的数据块
            pattern = r'"murl":"([^"]+)".*?"turl":"([^"]+)".*?"w":(\d+).*?"h":(\d+)'
            matches = re.findall(pattern, html)

            for m_url, t_url, w, h in matches:
                # 解码 URL
                m_url = m_url.replace("\\u003d", "=").replace("\\u0026", "&")
                t_url = t_url.replace("\\u003d", "=").replace("\\u0026", "&")

                images.append(ImageInfo(
                    url=m_url,
                    title="Bing Image",
                    author="Bing",
                    width=int(w),
                    height=int(h),
                    format=self._extract_format(m_url),
                    source=self.source_name,
                    preview_url=t_url,
                    download_url=m_url
                ))
        except Exception as e:
            print(f"解析 Bing 响应失败: {e}")

        return images

    def _map_resolution(self, resolution: str) -> str:
        """映射分辨率到 API 参数"""
        res_lower = resolution.lower()
        if "4k" in res_lower or "3840" in res_lower:
            return "Wallpaper"
        elif "2k" in res_lower or "2560" in res_lower:
            return "ExtraLarge"
        elif "1920" in res_lower or "1080" in res_lower:
            return "Large"
        elif "1280" in res_lower or "720" in res_lower:
            return "Medium"
        return "All"

    def _build_resolution_filter(self, resolution: str) -> str:
        """构建分辨率筛选条件"""
        filters = {
            "4k": "+filterui:imagesize-wallpaper",
            "2k": "+filterui:imagesize-1920x1200",
            "fhd": "+filterui:imagesize-1920x1080",
        }
        res_lower = resolution.lower().replace(" ", "")
        return filters.get(res_lower, "")

    def _build_color_filter(self, color: str) -> str:
        """构建颜色筛选条件"""
        color_map = {
            "黑白": "+filterui:color2-bw",
            "红色": "+filterui:color2-red",
            "橙色": "+filterui:color2-orange",
            "黄色": "+filterui:color2-yellow",
            "绿色": "+filterui:color2-green",
            "青色": "+filterui:color2-teal",
            "蓝色": "+filterui:color2-blue",
            "紫色": "+filterui:color2-purple",
            "粉色": "+filterui:color2-pink",
            "棕色": "+filterui:color2-brown",
            "黑色": "+filterui:color2-black",
            "白色": "+filterui:color2-white",
        }

        color_lower = color.lower()
        for cn, filt in color_map.items():
            if cn.lower() == color_lower:
                return filt
        return ""

    def _build_format_filter(self, format: str) -> str:
        """构建格式筛选条件"""
        format_map = {
            "jpg": "+filterui:photo-jpg",
            "png": "+filterui:photo-png",
            "gif": "+filterui:photo-gif",
            "webp": "+filterui:photo-transparent",
        }
        return format_map.get(format.lower(), "")

    def _map_color(self, color: str) -> Optional[str]:
        """映射颜色到 API 参数"""
        color_map = {
            "黑白": "Monochrome",
            "红色": "Red",
            "橙色": "Orange",
            "黄色": "Yellow",
            "绿色": "Green",
            "青色": "Teal",
            "蓝色": "Blue",
            "紫色": "Purple",
            "粉色": "Pink",
            "棕色": "Brown",
            "黑色": "Black",
            "白色": "White",
        }
        return color_map.get(color)

    @staticmethod
    def _extract_format(url: str) -> str:
        """从 URL 提取图片格式"""
        url_lower = url.lower()
        for ext in ['webp', 'png', 'jpg', 'jpeg', 'gif']:
            if f'.{ext}' in url_lower:
                return ext
        return 'jpg'

import re
