"""TS800X JLink 自定义异常."""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(Enum):
    """错误码枚举."""

    CONNECTION_FAILED = ("CONNECTION_FAILED", "连接失败", "检查 JLink USB 连接和目标供电")
    DEVICE_NOT_FOUND = ("DEVICE_NOT_FOUND", "设备未找到", "检查芯片是否上电，SWD 接线是否正确")
    CHIP_NOT_SUPPORTED = ("CHIP_NOT_SUPPORTED", "不支持的芯片", "当前仅支持 TS800X")
    UNLOCK_FAILED = ("UNLOCK_FAILED", "解锁失败", "检查 unlock 序列是否正确，芯片是否深度睡眠")
    FLASH_LOCKED = ("FLASH_LOCKED", "Flash 尚未解锁", "烧录前先调用 ts800x_unlock")
    ERASE_FAILED = ("ERASE_FAILED", "擦除失败", "检查 Flash 是否被保护")
    PROGRAM_FAILED = ("PROGRAM_FAILED", "烧录失败", "检查固件文件是否有效，Flash 是否已擦除")
    VERIFY_FAILED = ("VERIFY_FAILED", "校验失败", "烧录数据与 Flash 内容不匹配")
    FLASH_NOT_ERASED = ("FLASH_NOT_ERASED", "Flash 未擦除", "烧录前请先擦除 Flash")
    RTT_NOT_STARTED = ("RTT_NOT_STARTED", "RTT 未启动", "请先调用 rtt_start")
    CPU_NOT_HALTED = ("CPU_NOT_HALTED", "CPU 未暂停", "操作前请先 halt_cpu")
    DEEP_SLEEP = ("DEEP_SLEEP", "芯片深度睡眠", "SWD 已关闭，烧录时需按住 RESET 键")
    INVALID_PARAMETER = ("INVALID_PARAMETER", "参数无效", "检查参数值是否在有效范围内")
    UNKNOWN_ERROR = ("UNKNOWN_ERROR", "未知错误", "联系技术支持")

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def description(self) -> str:
        return self.value[1]

    @property
    def suggestion(self) -> str:
        return self.value[2]


class TS800XError(Exception):
    """TS800X JLink 基础异常."""

    def __init__(
        self,
        error_code: ErrorCode,
        detail: Optional[str] = None,
    ):
        self.error_code = error_code
        self.detail = detail or error_code.description
        super().__init__(f"[{error_code.code}] {self.detail}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.error_code.code,
            "description": self.error_code.description,
            "detail": self.detail,
            "suggestion": self.error_code.suggestion,
        }
