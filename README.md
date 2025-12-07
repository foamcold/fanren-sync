# Fanren Sync

`Fanren Sync` 是一个基于 FastAPI 构建的简单、安全、可自托管的 JSON 数据同步服务。它的灵感来源于一个简单的 Node.js 文件同步工具，并通过 Python 进行了重构和功能增强，特别加入了基于密码的认证和安全防护措施。本项目主要用于 SillyTavern 角色卡 “凡人修仙传” 云存档功能。

## ✨ 功能特性

- **安全认证**: 所有 API 请求都需要通过 URL 路径中包含的密码进行验证。
- **简单易用**: 提供四个核心 API 端点 (`list`, `load`, `save`, `delete`)，轻松实现数据的增删改查。
- **轻量高效**: 使用 FastAPI 构建，性能卓越，资源占用少。
- **异步处理**: 基于 `aiofiles` 进行异步文件操作，高并发场景下表现更佳。
- **易于部署**: 支持常规部署、Docker 和 Docker Compose 多种部署方式。
- **安全设计**:
  - 过滤存档名称，有效防止路径遍历攻击。
  - 根目录访问限制，保护服务不被随意探测。

## 🚀 快速开始

### 1. 环境准备

- Python 3.8+
- Git

### 2. 安装

```bash
# 克隆项目
git clone https://github.com/foamcold/fanren-sync
cd fanren-sync

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置

我们提供了一个环境变量示例文件 `.env.example`。你需要将它复制一份，并重命名为 `.env`，然后修改里面的密码。

```bash
# 复制示例文件
cp .env.example .env
```

然后，编辑新建的 `.env` 文件，设置你的同步密码：

```env
# .env
SYNC_PASSWORD=your_password
```
**警告**: 请务必使用一个强大且随机的密码，不要使用默认密码。

### 4. 运行 (开发环境)

```bash
python main.py
```
服务将以开发模式启动在 `http://localhost:8000`。

## 🐳 生产部署指南

### 方法二：使用 Docker

1.  **构建 Docker 镜像**:
    ```bash
    docker build -t fanren-sync .
    ```

2.  **运行 Docker 容器**:
    ```bash
    docker run -d \
      --name fanren-sync \
      -p 8000:8000 \
      -e SYNC_PASSWORD="your_password" \
      -v $(pwd)/data:/app/data \
      fanren-sync
    ```
    - `-d`: 后台运行
    - `-p`: 端口映射
    - `-e`: 设置环境变量
    - `-v`: 将本地的 `data` 目录挂载到容器中，实现数据持久化

### 方法三：使用 Docker Compose

这是最推荐的生产部署方式。它会自动处理镜像构建、环境变量注入和数据持久化。

1.  **配置环境变量**:
    Docker Compose 会使用 `${SYNC_PASSWORD}` 语法从你的 shell 环境中读取密码。在启动前，请先设置环境变量：
    ```bash
    # Linux / macOS
    export SYNC_PASSWORD="your_password"

    # Windows (CMD)
    set SYNC_PASSWORD="your_password"

    # Windows (PowerShell)
    $env:SYNC_PASSWORD="your_password"
    ```

2.  **启动服务**:
    ```bash
    docker-compose up -d --build
    ```

3.  **停止服务**:
    ```bash
    docker-compose down
    ```

## 📚 API 使用说明

所有 API 的 URL 基础路径为 `http://<your-host>:<port>/<your-password>`。

以下示例中，我们假设 `SYNC_PASSWORD` 为 `your_password`。

客户端需要使用的基础 URL 示例：
`http://localhost:8000/your_password`

---

### 列出所有存档

- **方法**: `GET`
- **路径**: `/list`
- **示例**: `GET http://localhost:8000/your_password/api/list`
- **成功响应**:
  ```json
  {
    "success": true,
    "archives": ["test_data_1", "my_notes"]
  }
  ```

---

### 加载存档

- **方法**: `GET`
- **路径**: `/load`
- **参数**: `archiveName` (Query String)
- **示例**: `GET http://localhost:8000/your_password/api/load?archiveName=test_data_1`
- **成功响应**:
  ```json
  {
    "success": true,
    "data": { "key": "value", "notes": [1, 2, 3] }
  }
  ```
- **失败响应 (未找到)**:
  ```json
  {
    "detail": "存档未找到"
  }
  ```

---

### 保存存档

- **方法**: `POST`
- **路径**: `/save`
- **请求体**:
  ```json
  {
    "archiveName": "test_data_1",
    "data": { "key": "new value", "notes": [4, 5, 6] }
  }
  ```
  *(注：如果 `archiveName` 缺失，会尝试从 `data._internalName` 获取)*
- **示例**: `POST http://localhost:8000/your_password/api/save`
- **成功响应**:
  ```json
  {
    "success": true,
    "message": "存档已成功保存"
  }
  ```

---

### 删除存档

- **方法**: `DELETE`
- **路径**: `/delete`
- **参数**: `archiveName` (Query String)
- **示例**: `DELETE http://localhost:8000/your_password/api/delete?archiveName=test_data_1`
- **成功响应**:
  ```json
  {
    "success": true,
    "message": "存档已成功删除"
  }
  ```
