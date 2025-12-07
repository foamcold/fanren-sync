# --- Stage 1: Build ---
# 使用官方 Python 镜像作为基础镜像
FROM python:3.11-slim AS builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 安装依赖
# 首先只复制 requirements.txt 以便利用 Docker 的层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final Image ---
# 创建一个更小的最终镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 从 builder 阶段复制已安装的依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY . .

# --- 权限设置 ---
# 默认以 root 运行，避免挂载卷时的权限问题
# 如果需要非 root 运行，请确保宿主机挂载目录的权限与容器内用户匹配

# 暴露端口
EXPOSE 8000

# 定义容器启动时执行的命令
# 使用 python main.py 启动，以便应用自定义日志配置和启动检查逻辑
CMD ["python", "main.py"]