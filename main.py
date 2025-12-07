import os
import re
import uvicorn
import aiofiles
import aiofiles.os
from typing import Any
from fastapi import FastAPI, status, Depends, HTTPException, Path, APIRouter
from fastapi.responses import JSONResponse
import json
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# --- 应用实例 ---
app = FastAPI(
    title="fanren-sync",
    version="0.1.0",
    description="一个简单、安全、自托管的 json 数据同步服务。",
    docs_url=None,  # 禁用默认的 /docs
    redoc_url=None,  # 禁用默认的 /redoc
)

# --- 配置 ---
sync_password = os.getenv("sync_password")
data_dir = os.path.join(os.path.dirname(__file__), "data")


# --- pydantic 模型 ---
class SaveData(BaseModel):
    """定义保存请求的数据结构"""
    data: Any


# --- 安全与依赖 ---
def sanitize_filename(filename: str) -> str:
    """
    清理文件名，只允许字母、数字、下划线和连字符。
    防止路径遍历攻击。
    """
    # 移除非法字符
    sanitized = re.sub(r'[^a-za-z0-9_\-]', '', filename)
    # 防止文件名过长
    return sanitized[:100]

async def verify_password(password: str = Path(..., title="访问密码")):
    """
    fastapi 依赖项，用于验证 url 路径中的密码。
    """
    if not sync_password or password != sync_password:
        raise HTTPException(
            status_code=status.http_403_forbidden,
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
            status_code=status.http_500_internal_server_error,
            detail=f"无法列出存档: {e}",
        )


@router.get("/load/{archive_name}", summary="加载存档")
async def load_archive(archive_name: str):
    """根据名称加载一个 json 存档。"""
    safe_filename = sanitize_filename(archive_name)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")
    
    if not await aiofiles.os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="存档未找到")

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return JSONResponse(content={"success": True, "data": json.loads(content)})
    except Exception as e:
        raise HTTPException(
            status_code=status.http_500_internal_server_error,
            detail=f"无法加载存档: {e}",
        )


@router.post("/save/{archive_name}", summary="保存存档")
async def save_archive(archive_name: str, payload: SaveData):
    """创建或更新一个 json 存档。"""
    safe_filename = sanitize_filename(archive_name)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")

    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload.data, indent=2, ensure_ascii=False))
        return {"success": True, "message": "存档已成功保存"}
    except Exception as e:
        raise HTTPException(
            status_code=status.http_500_internal_server_error,
            detail=f"无法保存存档: {e}",
        )


@router.delete("/delete/{archive_name}", summary="删除存档")
async def delete_archive(archive_name: str):
    """根据名称删除一个 json 存档。"""
    safe_filename = sanitize_filename(archive_name)
    file_path = os.path.join(data_dir, f"{safe_filename}.json")

    if not await aiofiles.os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="存档未找到")

    try:
        await aiofiles.os.remove(file_path)
        return {"success": True, "message": "存档已成功删除"}
    except Exception as e:
        raise HTTPException(
            status_code=status.http_500_internal_server_error,
            detail=f"无法删除存档: {e}",
        )

# --- 应用设置 ---
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行
    await aiofiles.os.makedirs(data_dir, exist_ok=True)
    yield
    # 应用关闭时执行 (如果需要)

app.router.lifespan = lifespan


@app.get("/")
async def root():
    """根路径访问被禁止。"""
    return JSONResponse(
        status_code=status.http_403_forbidden,
        content={"success": False, "error": "访问被拒绝。请使用正确的 api 路径和密码。"},
    )

# 将带有密码保护的路由器包含到主应用中
# 所有的 api 路径都会是 /{password}/...
app.include_router(router, prefix="/{password}")

# --- 运行应用 ---
if __name__ == "__main__":
    if not sync_password:
        print("错误: 环境变量 sync_password 未设置。")
        print("请在项目根目录创建一个 .env 文件并设置 sync_password。")
    else:
        print(f"--- 启动 fanren-sync v{app.version} ---")
        print(f"数据存储目录: {data_dir}")
        print("服务已启动。使用 ctrl+c 停止服务。")
        uvicorn.run(app, host="0.0.0.0", port=8000)
