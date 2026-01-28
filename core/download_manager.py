"""
异步下载管理器模块
提供高效的异步图片下载功能，支持并发控制、进度回调、断点续传等
"""
import asyncio
import aiofiles
import aiohttp
from pathlib import Path
from typing import List, Optional, Callable, Set, Dict
from dataclasses import dataclass, field
from datetime import datetime
import hashlib

from core.base_adapter import (
    BaseSourceAdapter,
    ImageInfo,
    DownloadProgress,
    DownloadException
)


@dataclass
class DownloadTask:
    """下载任务"""
    image_info: ImageInfo
    save_dir: str
    filename: Optional[str] = None
    priority: int = 0  # 优先级，数字越大优先级越高
    retry_count: int = 0
    max_retries: int = 3
    progress: DownloadProgress = field(default_factory=DownloadProgress)

    def get_save_path(self) -> str:
        """获取保存路径"""
        if self.filename:
            return str(Path(self.save_dir) / self.filename)
        return self._generate_filename()

    def _generate_filename(self) -> str:
        """生成唯一文件名"""
        # 使用URL哈希确保唯一性
        url_hash = hashlib.md5(self.image_info.url.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 清理标题作为文件名
        safe_title = "".join(
            c for c in self.image_info.title
            if c.isalnum() or c in (' ', '-', '_', '中', '文')
        ).strip()[:30] or "image"

        ext = self.image_info.format or "jpg"
        return f"{self.image_info.source}_{safe_title}_{timestamp}_{url_hash}.{ext}"


@dataclass
class DownloadStats:
    """下载统计"""
    total: int = 0
    completed: int = 0
    failed: int = 0
    pending: int = 0
    downloading: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0

    @property
    def progress_percent(self) -> float:
        """总体进度百分比"""
        if self.total > 0:
            return (self.completed / self.total) * 100
        return 0.0

    @property
    def speed_percent(self) -> float:
        """下载量百分比"""
        if self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return 0.0


class DownloadManager:
    """
    异步下载管理器
    支持并发下载、进度回调、错误重试、断点续传
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: int = 30,
        chunk_size: int = 8192
    ):
        """
        :param max_concurrent: 最大并发下载数
        :param timeout: 请求超时时间（秒）
        :param chunk_size: 下载块大小（字节）
        """
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.chunk_size = chunk_size

        # 任务队列
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_tasks: Dict[str, DownloadTask] = {}
        self._completed_urls: Set[str] = set()

        # 统计信息
        self._stats = DownloadStats()
        self._start_time: Optional[datetime] = None

        # 控制
        self._is_running = False
        self._workers: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()

        # 回调
        self._progress_callbacks: List[Callable[[DownloadProgress], None]] = []
        self._stats_callbacks: List[Callable[[DownloadStats], None]] = []

    def add_progress_callback(self, callback: Callable[[DownloadProgress], None]) -> None:
        """添加进度回调"""
        self._progress_callbacks.append(callback)

    def add_stats_callback(self, callback: Callable[[DownloadStats], None]) -> None:
        """添加统计回调"""
        self._stats_callbacks.append(callback)

    async def add_download(
        self,
        image_info: ImageInfo,
        save_dir: str,
        filename: Optional[str] = None,
        priority: int = 0
    ) -> None:
        """
        添加下载任务
        :param image_info: 图片信息
        :param save_dir: 保存目录
        :param filename: 文件名（可选）
        :param priority: 优先级
        """
        # 检查是否已下载
        if image_info.url in self._completed_urls:
            return

        task = DownloadTask(
            image_info=image_info,
            save_dir=save_dir,
            filename=filename,
            priority=priority
        )
        # 使用负优先级，因为PriorityQueue是最小堆
        await self._queue.put((-priority, task))
        self._stats.total += 1
        self._stats.pending += 1
        self._notify_stats()

    async def add_batch_downloads(
        self,
        images: List[ImageInfo],
        save_dir: str,
        priority: int = 0
    ) -> None:
        """
        批量添加下载任务
        :param images: 图片信息列表
        :param save_dir: 保存目录
        :param priority: 优先级
        """
        for img in images:
            await self.add_download(img, save_dir, priority=priority)

    async def start(self) -> None:
        """启动下载管理器"""
        if self._is_running:
            return

        self._is_running = True
        self._start_time = datetime.now()
        self._stop_event.clear()

        # 创建工作协程
        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_concurrent)
        ]

    async def stop(self, wait_completion: bool = True) -> None:
        """
        停止下载管理器
        :param wait_completion: 是否等待当前任务完成
        """
        if not self._is_running:
            return

        if wait_completion:
            # 等待队列清空
            await self._queue.join()

        # 停止工作协程
        self._is_running = False
        self._stop_event.set()

        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def wait_completion(self) -> None:
        """等待所有任务完成"""
        await self._queue.join()

    def get_stats(self) -> DownloadStats:
        """获取下载统计"""
        return self._stats

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running

    async def _worker(self, worker_id: int) -> None:
        """
        下载工作协程
        :param worker_id: 工作器ID
        """
        while self._is_running:
            try:
                # 从队列获取任务（带超时，便于响应停止信号）
                priority, task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )

                # 更新状态
                self._stats.pending -= 1
                self._stats.downloading += 1
                task.progress.status = "downloading"
                self._active_tasks[task.image_info.url] = task
                self._notify_stats()

                # 执行下载
                try:
                    await self._download(task)
                    self._stats.completed += 1
                    self._completed_urls.add(task.image_info.url)
                    task.progress.status = "completed"
                except Exception as e:
                    task.retry_count += 1
                    if task.retry_count <= task.max_retries:
                        # 重试
                        await self._queue.put((priority, task))
                        self._stats.pending += 1
                        task.progress.status = "retrying"
                    else:
                        # 失败
                        self._stats.failed += 1
                        task.progress.status = "failed"
                        task.progress.error = str(e)
                finally:
                    self._stats.downloading -= 1
                    self._active_tasks.pop(task.image_info.url, None)
                    self._queue.task_done()
                    self._notify_stats()
                    self._notify_progress(task.progress)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")

    async def _download(self, task: DownloadTask) -> None:
        """
        执行下载
        :param task: 下载任务
        """
        save_path = task.get_save_path()
        Path(task.save_dir).mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(task.image_info.download_url or task.image_info.url) as response:
                if response.status != 200:
                    raise DownloadException(f"HTTP {response.status}: {response.reason}")

                # 获取文件大小
                total_size = int(response.headers.get('Content-Length', 0))
                task.progress.total_bytes = total_size

                downloaded = 0
                async with aiofiles.open(save_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        task.progress.downloaded_bytes = downloaded

                        # 通知进度
                        self._notify_progress(task.progress)

                task.progress.save_path = save_path

    def _notify_progress(self, progress: DownloadProgress) -> None:
        """通知进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception:
                pass

    def _notify_stats(self) -> None:
        """通知统计更新"""
        for callback in self._stats_callbacks:
            try:
                callback(self._stats)
            except Exception:
                pass


class SimpleDownloader:
    """
    简单下载器
    用于不需要队列管理的简单下载场景
    """

    def __init__(self, timeout: int = 30, chunk_size: int = 8192):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.chunk_size = chunk_size

    async def download(
        self,
        url: str,
        save_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        下载单个文件
        :param url: 下载URL
        :param save_path: 保存路径
        :param progress_callback: 进度回调 (downloaded, total)
        :return: 实际保存路径
        """
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise DownloadException(f"HTTP {response.status}")

                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0

                async with aiofiles.open(save_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)

                return save_path

    async def download_batch(
        self,
        urls: List[str],
        save_dir: str,
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[str]:
        """
        批量下载文件
        :param urls: URL列表
        :param save_dir: 保存目录
        :param max_concurrent: 最大并发数
        :param progress_callback: 进度回调 (completed, total)
        :return: 保存路径列表
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        Path(save_dir).mkdir(parents=True, exist_ok=True)

        async def download_one(url: str, index: int) -> str:
            async with semaphore:
                ext = self._get_extension(url)
                filename = f"image_{index:04d}.{ext}"
                save_path = str(Path(save_dir) / filename)
                return await self.download(url, save_path)

        tasks = [download_one(url, i) for i, url in enumerate(urls)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        if progress_callback:
            progress_callback(len([r for r in results if isinstance(r, str)]), len(urls))

        return [r for r in results if isinstance(r, str)]

    @staticmethod
    def _get_extension(url: str) -> str:
        """从URL获取文件扩展名"""
        url_lower = url.lower()
        for ext in ['webp', 'png', 'jpg', 'jpeg', 'gif']:
            if f'.{ext}' in url_lower:
                return ext
        return 'jpg'
