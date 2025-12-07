import os
import re
import uvicorn
import aiofiles
import aiofiles.os
import logging
import sys
import urllib.parse
from typing import Any
from fastapi import FastAPI, status, Depends, HTTPException, Path, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# 加载 .env 文件中的环境变量
load_dotenv()

# --- 日志配置 ---
class TranslationFilter(logging.Filter):
    """
    日志过滤器：
    1. 将英文日志翻译成中文
    2. 将 0.0.0.0 和 127.0.0.1 替换为 localhost
    3. URL 解码
    """
    def filter(self, record):
        msg = record.msg
        args = record.args

        # 如果有参数，先进行格式化，生成最终的消息字符串
        # 这样可以解决 %d, %s 等占位符无法正确显示的问题
        if args:
            try:
                msg = msg % args
            except Exception:
                # 如果格式化失败，保留原样，避免崩溃
                pass
            # 格式化后清空参数，防止二次格式化
            record.args = ()

        if isinstance(msg, str):
            # URL 解码 (让日志中的中文路径/参数可读)
            if "%" in msg:
                try:
                    msg = urllib.parse.unquote(msg)
                except Exception:
                    pass

            # 替换 IP 地址 (在格式化之后进行，这样参数里的 IP 也会被替换)
            msg = msg.replace("0.0.0.0", "localhost").replace("127.0.0.1", "localhost")
            
            # 翻译常见 Uvicorn 日志
            if "Started server process" in msg:
                msg = msg.replace("Started server process", "服务进程已启动")
            elif "Waiting for application startup" in msg:
                msg = "正在等待应用启动..."
            elif "Application startup complete" in msg:
                msg = "应用启动完成"
            elif "Uvicorn running on" in msg:
                msg = msg.replace("Uvicorn running on", "Uvicorn 运行于")
                msg = msg.replace("(Press CTRL+C to quit)", "(按 CTRL+C 退出)")
            elif "Shutting down" in msg:
                msg = "正在关闭服务..."
            elif "Waiting for application shutdown" in msg:
                msg = "正在等待应用关闭..."
            elif "Application shutdown complete" in msg:
                msg = "应用关闭完成"
            elif "Finished server process" in msg:
                msg = msg.replace("Finished server process", "服务进程已结束")
            
            record.msg = msg
        return True

# 强制统一日志格式：时间 - 级别 - 内容
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "translation": {
            "()": TranslationFilter,
        },
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
            "filters": ["translation"],
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

logger = logging.getLogger("app")

# --- 配置 ---
# 优先读取大写 SYNC_PASSWORD，兼容小写 sync_password
sync_password = os.getenv("SYNC_PASSWORD") or os.getenv("sync_password")
data_dir = os.path.join(os.path.dirname(__file__), "data")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行
    await aiofiles.os.makedirs(data_dir, exist_ok=True)
    yield
    # 应用关闭时执行 (如果需要)


# --- 应用实例 ---
app = FastAPI(
    title="fanren-sync",
    version="0.1.0",
    description="一个简单、安全、自托管的 json 数据同步服务。",
    docs_url=None,  # 禁用默认的 /docs
    redoc_url=None,  # 禁用默认的 /redoc
    lifespan=lifespan,
)

# --- CORS 配置 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，根据需要可限制
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

# --- 异常处理 ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理，防止堆栈信息泄露"""
    # 在这里可以添加日志记录逻辑
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": "服务器内部错误"},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一 HTTP 异常返回格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )

# --- pydantic 模型 ---
class SaveData(BaseModel):
    """定义保存请求的数据结构"""
    data: Any
    archiveName: str | None = None  # 兼容旧版 API，允许在 body 中传递 archiveName


# --- 安全与依赖 ---
def sanitize_filename(filename: str) -> str:
    """
    清理文件名，允许字母(含中文等Unicode字符)、数字、下划线和连字符。
    防止路径遍历攻击。
    """
    # 移除非法字符 (保留 Unicode 字母和数字)
    # \w 在 Python 3 的 re 模块中默认包含 Unicode 字符 (字母, 数字, 下划线)
    # 但为了更精确控制，我们排除掉除了 字母、数字、下划线、连字符 以外的字符
    # 注意：为了安全起见，我们仍然要防止路径遍历 (.. / 等)
    
    # 简单粗暴的方法：只保留 字母(Unicode)、数字、下划线、连字符
    # Python 的 \w 匹配 [a-zA-Z0-9_] 以及其他语言的字母数字
    # 所以我们只需要移除 [^\w\-] 即可
    sanitized = re.sub(r'[^\w\-]', '', filename)
    
    # 防止文件名过长
    return sanitized[:100]

async def verify_password(password: str = Path(..., title="访问密码")):
    """
    fastapi 依赖项，用于验证 url 路径中的密码。
    """
    if not sync_password or password != sync_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无效的访问密码",
        )

# 创建一个带有密码验证依赖的 api 路由器
router = APIRouter(dependencies=[Depends(verify_password)])


# --- api 端点 ---
@router.get("/list", summary="列出所有存档")
async def list_archives():
    """列出所有已保存的 json 存档文件。"""
    try:
        files = await aiofiles.os.listdir(data_dir)
        archives = [f.replace(".json", "") for f in files if f.endswith(".json")]
        return {"success": True, "archives": archives}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法列出存档: {str(e)}",
        )


@router.get("/load", summary="加载存档")
async def load_archive(archiveName: str):
    """根据名称加载一个 json 存档。"""
    safe_filename = sanitize_filename(archiveName)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")
    
    if not await aiofiles.os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="存档未找到")

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return JSONResponse(content={"success": True, "data": json.loads(content)})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法加载存档: {str(e)}",
        )


@router.post("/save", summary="保存存档")
async def save_archive(payload: SaveData):
    """创建或更新一个 json 存档。"""
    # 1. 尝试从 payload 顶层获取 archiveName
    archive_name = payload.archiveName
    
    # 2. 如果没有，尝试从 data._internalName 获取
    if not archive_name and isinstance(payload.data, dict):
        archive_name = payload.data.get("_internalName")
    
    if not archive_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive name is required (in body 'archiveName' or 'data._internalName')"
        )

    safe_filename = sanitize_filename(archive_name)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")

    logger.info("正在保存存档: 原始名称='%s', 安全名称='%s'", archive_name, safe_filename)

    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload.data, indent=2, ensure_ascii=False))
        return {"success": True, "message": "存档已成功保存"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法保存存档: {str(e)}",
        )


@router.delete("/delete", summary="删除存档")
async def delete_archive(archiveName: str):
    """根据名称删除一个 json 存档。"""
    safe_filename = sanitize_filename(archiveName)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")

    if not await aiofiles.os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="存档未找到")

    try:
        await aiofiles.os.remove(file_path)
        return {"success": True, "message": "存档已成功删除"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"无法删除存档: {str(e)}",
        )



@app.get("/")
async def root():
    """根路径访问被禁止。"""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"success": False, "error": "访问被拒绝。请使用正确的 api 路径和密码。"},
    )

# 将带有密码保护的路由器包含到主应用中
# 所有的 api 路径都会是 /{password}/api/...
app.include_router(router, prefix="/{password}/api")

# --- 运行应用 ---
def print_banner(host, port, version, data_dir):
    """打印带边框的启动横幅"""
    def get_width(s):
        return sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in s)

    content_lines = [
        f"Fanren-Sync v{version} 启动成功",
        "",
        f"数据目录: {data_dir}",
        f"服务地址: http://{'localhost' if host == '0.0.0.0' else host}:{port}"
    ]
    
    # 计算最大宽度
    max_width = max(get_width(line) for line in content_lines)
    # 确保最小宽度，避免太窄
    max_width = max(max_width, 40)
    box_width = max_width + 4  # 左右各留2空格
    
    print(f"┌{'─' * box_width}┐")
    for line in content_lines:
        padding = box_width - get_width(line)
        # 居中显示标题，其他左对齐
        if "启动成功" in line:
            left_pad = padding // 2
            right_pad = padding - left_pad
            print(f"│{' ' * left_pad}{line}{' ' * right_pad}│")
        else:
            print(f"│  {line}{' ' * (padding - 2)}│")
    print(f"└{'─' * box_width}┘")

if __name__ == "__main__":
    if not sync_password:
        print("错误: 环境变量 SYNC_PASSWORD 未设置。")
        print("请在项目根目录创建一个 .env 文件并设置 SYNC_PASSWORD。")
    else:
        host = "0.0.0.0"
        port = 8000
        print_banner(host, port, app.version, data_dir)
        # 使用自定义日志配置启动
        uvicorn.run(app, host=host, port=port, log_config=LOGGING_CONFIG)
