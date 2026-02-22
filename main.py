import os
import asyncio
import logging
import aiofiles
import aiohttp  
from typing import List, Optional
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.api.message_components import *

logger = logging.getLogger(__name__)

file_lock = asyncio.Lock()

class ImageManager:
    """图片管理类"""
    def __init__(self):
        self.imgs_folder = "imgs"
        self.supported_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
        self._init_folder()

    def _init_folder(self):
        """初始化图片文件夹"""
        if not os.path.exists(self.imgs_folder):
            os.makedirs(self.imgs_folder)
            logger.info("Created images folder")

    async def get_image_list(self):
        """获取有效图片列表"""
        async with file_lock:
            try:
                files = await asyncio.to_thread(os.listdir, self.imgs_folder)
                return [f for f in files if os.path.splitext(f)[1].lower() in self.supported_extensions]
            except Exception as e:
                logger.error(f"Error getting image list: {str(e)}")
                return []

    async def delete_image(self, filename: str):
        """安全删除图片文件"""
        async with file_lock:
            file_path = os.path.join(self.imgs_folder, filename)
            try:
                if os.path.exists(file_path):
                    await asyncio.to_thread(os.remove, file_path)
                    logger.info(f"Deleted image: {filename}")
                    return True
                logger.warning(f"Attempted to delete non-existent file: {filename}")
                return False
            except Exception as e:
                logger.error(f"Error deleting image {filename}: {str(e)}")
                return False

    async def generate_and_save_image(self, url, filename):
        async with file_lock:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get(url) as response:
                        content = await response.read()  # 异步读取响应内容
                        file_path = os.path.join(self.imgs_folder, filename)
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(content)  # 异步写入文件
                        logger.info(f"Successfully saved image: {filename}")
                        return True
            except aiohttp.ClientError as e:
                logger.error(f"HTTP Error saving {filename}: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error saving {filename}: {str(e)}")
                return False

image_manager = ImageManager()

async def fetch_setu(
        r18: int = 1,
        num: int = 1,
        tags: Optional[List[List[str]]] = None,
        size: List[str] = None,
        uid: List[int] = None,
        keyword: str = None,
        proxy: str = None,
        exclude_ai: bool = None,
        aspect_ratio: str = None
) -> Optional[List[dict]]:
    url = "https://api.lolicon.app/setu/v2"
    params = {
        "r18": r18,
        "num": max(1, min(20, num)),
        "excludeAI": exclude_ai,
    }

    if tags: params["tag"] = tags
    if size: params["size"] = size
    if uid: params["uid"] = uid[:20]
    if keyword: params["keyword"] = keyword
    if proxy: params["proxy"] = proxy
    if aspect_ratio: params["aspectRatio"] = aspect_ratio

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=params) as response:
                data = await response.json() 

                if data.get("error"):
                    logger.warning(f"API Error: {data['error']}")
                    return None

                return data.get("data", [])

    except aiohttp.ClientError as e:
        logger.error(f"HTTP Request Failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")
        return None

@register("astrbot_plugin_lolicon", "hello", "涩涩", "1.3", "https://github.com/ttq7/astrbot_plugin_Lolicon")
class ArknightsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.image_manager = image_manager

    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理所有消息事件"""
        try:
            text = event.message_str.lower()
            
            # R18 模式: 检查是否包含 "色色" 或 "涩涩"
            if any(keyword in text for keyword in ["色色", "涩涩"]):
                await event.send(event.plain_result("皇上又来了 喵"))
                return await self.handle_image_request(event, r18_mode=True)
            
            # 非 R18 模式: 检查是否包含 "想要" 或 "我要"
            elif any(keyword in text for keyword in ["想要", "我要"]):
                await event.send(event.plain_result("好的，为您准备健康的内容~"))
                return await self.handle_image_request(event, r18_mode=False)

        except Exception as e:
            logger.error(f"Message handler error: {str(e)}")
            return event.plain_result(f"插件异常: {str(e)}")

        # 如果没有命中任何关键词，则返回空结果，不触发任何操作
        return event.empty_result()

    async def handle_image_request(self, event: AstrMessageEvent, r18_mode: bool = True) -> MessageEventResult:
        """异步处理图片请求全流程，根据 r18_mode 参数决定请求类型"""
        try:
            # 根据模式设置R18参数和回复语
            if r18_mode:
                # R18模式
                r18_value = 1
                no_data_reply = "皇上不行了 喵"
                no_url_reply = "皇上没戴那个 喵"
                save_fail_reply = "皇上不能内射 喵"
                success_reply = "啊 出来了 喵"
                fail_cleanup_reply = "完了涩涩没有打扫干净"
                send_fail_reply = "皇上我处理不好 喵"
                general_error_reply = "处理请求时发生错误，请联系管理员"
            else:
                # 非R18模式
                r18_value = 0
                no_data_reply = "暂时没有健康内容可以提供哦"
                no_url_reply = "获取健康内容链接失败"
                save_fail_reply = "保存健康内容时出现问题"
                success_reply = "这是您要的健康内容哦~"
                fail_cleanup_reply = "内容已处理，但清理时出现问题。"
                send_fail_reply = "网络不佳，健康内容没送达到。"
                general_error_reply = "获取内容时出错啦，请稍后再试~"

            results = await fetch_setu(
                r18=r18_value, # 使用动态决定的 r18 值
                tags=[[], []],
                exclude_ai=True,
                aspect_ratio="gt1",
                num=1
            )
            if not results:
                return event.plain_result(no_data_reply)

            item = results[0]
            original_url = item['urls'].get("original")
            if not original_url:
                return event.plain_result(no_url_reply)

            filename = f"{item['pid']}_p{item['p']}.{item['ext']}"

            save_success = await self.image_manager.generate_and_save_image(original_url, filename)
            if not save_success:
                return event.plain_result(save_fail_reply)

            image_path = os.path.join(self.image_manager.imgs_folder, filename)
            message_chain = event.make_result().file_image(image_path)
            
            # 异步发送图片
            try:
                await event.send(message_chain)
                logger.info(f"Image sent: {filename} (R18: {r18_mode})")
                
                # 延迟删除（避免发送过程中文件被删除）
                await asyncio.sleep(1)
                delete_success = await self.image_manager.delete_image(filename)
                return event.plain_result(success_reply) if delete_success \
                    else event.plain_result(fail_cleanup_reply)

            except Exception as e:
                logger.warning(f"Send failed for {filename}: {str(e)}")
                await self.image_manager.delete_image(filename)  
                return event.plain_result(send_fail_reply)

        except Exception as e:
            logger.error(f"Request handling failed: {str(e)}")
            return event.plain_result(general_error_reply)

    async def terminate(self):
        """插件终止时清理图片"""
        try:
            image_files = await self.image_manager.get_image_list()
            if image_files:
                await asyncio.gather(*(self.image_manager.delete_image(f) for f in image_files))
            logger.info("Plugin terminated, cleaned up %d images", len(image_files))
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

