import httpx


class VideoLectureError(Exception):
    pass


class DownloadError(VideoLectureError):
    pass


class TranscribeError(VideoLectureError):
    pass


class LLMError(VideoLectureError):
    pass


class LLMConfigurationError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class UnsupportedPlatformError(DownloadError):
    pass


class TranscriptionTimeoutError(TranscribeError):
    pass


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        return True
    if isinstance(error, TranscribeError) and "timeout" in str(error).lower():
        return True
    return False


def format_error_for_user(error: Exception) -> str:
    if isinstance(error, LLMAuthenticationError):
        return "API 密钥无效或已过期，请检查配置"
    if isinstance(error, LLMConfigurationError):
        return f"LLM 配置不完整：{error}"
    if isinstance(error, UnsupportedPlatformError):
        return f"不支持的视频平台：{error}"
    if isinstance(error, TranscriptionTimeoutError):
        return "语音转写超时，请尝试使用云转写模式"
    if isinstance(error, DownloadError):
        return f"视频下载失败：{error}"
    if isinstance(error, TranscribeError):
        return f"语音转写失败：{error}"
    return f"处理失败：{error}"
