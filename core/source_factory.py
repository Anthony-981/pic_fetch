"""
图片源工厂模块
负责创建和管理各种图片源适配器
"""
from typing import Dict, Type, List, Optional
from core.base_adapter import BaseSourceAdapter, ValidationException


class SourceFactory:
    """
    图片源工厂类
    使用工厂模式管理和创建适配器实例
    """

    # 注册的适配器类字典
    _adapters: Dict[str, Type[BaseSourceAdapter]] = {}

    @classmethod
    def register(cls, name: str, adapter_class: Type[BaseSourceAdapter]) -> None:
        """
        注册一个新的适配器
        :param name: 适配器名称
        :param adapter_class: 适配器类
        """
        cls._adapters[name] = adapter_class

    @classmethod
    def unregister(cls, name: str) -> None:
        """
        取消注册适配器
        :param name: 适配器名称
        """
        if name in cls._adapters:
            del cls._adapters[name]

    @classmethod
    def create(cls, name: str, **kwargs) -> BaseSourceAdapter:
        """
        创建适配器实例
        :param name: 适配器名称
        :param kwargs: 传递给适配器的参数
        :return: 适配器实例
        :raises ValidationException: 如果适配器不存在
        """
        adapter_class = cls._adapters.get(name)
        if not adapter_class:
            raise ValidationException(f"未知的图片源: {name}")
        return adapter_class(**kwargs)

    @classmethod
    def get_available_sources(cls) -> List[str]:
        """
        获取所有已注册的图片源名称列表
        :return: 图片源名称列表
        """
        return list(cls._adapters.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """
        检查适配器是否已注册
        :param name: 适配器名称
        :return: 是否已注册
        """
        return name in cls._adapters

    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        """
        获取图片源的显示名称映射
        :return: {内部名称: 显示名称}
        """
        display_map = {
            "unsplash": "Unsplash（高清网图）",
            "pexels": "Pexels（免费图库）",
            "pixabay": "Pixabay（素材库）",
            "wallhaven": "Wallhaven（壁纸）",
            "avatar": "多抓鱼（头像）",
            "baidu": "百度图片",
            "google": "Google图片",
            "bing": "Bing图片",
        }
        return {k: v for k, v in display_map.items() if k in cls._adapters}

    @classmethod
    def get_source_by_display_name(cls, display_name: str) -> Optional[str]:
        """
        根据显示名称获取内部名称
        :param display_name: 显示名称
        :return: 内部名称，如果找不到返回None
        """
        display_map = cls.get_display_names()
        for internal, display in display_map.items():
            if display == display_name:
                return internal
        return None


class SourceManager:
    """
    图片源管理器
    管理多个适配器实例的生命周期
    """

    def __init__(self):
        self._active_adapters: Dict[str, BaseSourceAdapter] = {}
        self._factory = SourceFactory()

    async def get_adapter(
        self,
        source_name: str,
        config: Optional[Dict] = None,
        refresh: bool = False
    ) -> BaseSourceAdapter:
        """
        获取适配器实例（单例模式）
        :param source_name: 图片源名称
        :param config: 配置参数
        :param refresh: 是否强制刷新实例
        :return: 适配器实例
        """
        if refresh or source_name not in self._active_adapters:
            adapter = self._factory.create(source_name, **(config or {}))
            await adapter.validate()
            self._active_adapters[source_name] = adapter
        return self._active_adapters[source_name]

    async def close_adapter(self, source_name: str) -> None:
        """
        关闭指定适配器
        :param source_name: 图片源名称
        """
        if source_name in self._active_adapters:
            await self._active_adapters[source_name].close()
            del self._active_adapters[source_name]

    async def close_all(self) -> None:
        """关闭所有活动适配器"""
        for adapter in self._active_adapters.values():
            await adapter.close()
        self._active_adapters.clear()

    def get_active_sources(self) -> List[str]:
        """获取所有活动的图片源"""
        return list(self._active_adapters.keys())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all()


# 适配器注册装饰器
def register_adapter(name: str):
    """
    适配器注册装饰器
    使用方式:
        @register_adapter("unsplash")
        class UnsplashAdapter(BaseSourceAdapter):
            ...
    """
    def decorator(adapter_class: Type[BaseSourceAdapter]):
        SourceFactory.register(name, adapter_class)
        return adapter_class
    return decorator
