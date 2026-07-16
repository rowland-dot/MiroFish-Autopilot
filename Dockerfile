# MiroFish — single-container production image (Hugging Face Spaces compatible)
# Stage 1 builds the Vue frontend; stage 2 runs Flask serving the SPA + /api
# on one port (7860). Secrets (LLM_API_KEY, ZEP_API_KEY, ACCESS_CODE, …) come
# from environment variables — never baked into the image.

# ---------- Stage 1: frontend build ----------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm ci --prefix frontend
COPY frontend ./frontend
# i18n 从仓库根目录 locales/ 动态导入（import.meta.glob ../../locales）
COPY locales ./locales
RUN npm run build --prefix frontend

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Python 依赖（利用层缓存）
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen

# 后端源码 + 根目录 locales（后端 t() 同样读取）+ 构建好的前端
COPY backend ./backend
COPY locales ./locales
COPY --from=frontend /build/frontend/dist ./frontend/dist

ENV FLASK_PORT=7860 \
    FLASK_DEBUG=false \
    PYTHONUNBUFFERED=1

# HF Spaces 以非 root 运行；uploads 是唯一需要写权限的目录（临时盘）
RUN useradd -m -u 1000 appuser \
    && mkdir -p backend/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

CMD ["backend/.venv/bin/python", "backend/run.py"]
