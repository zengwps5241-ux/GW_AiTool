# ========== Stage 2: 构建前端 ==========
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com \
 && npm ci

COPY frontend/ ./
RUN npm run build


# ========== Stage 3: 后端运行镜像 ==========
FROM gokagent-backend:base

#安装skills所需的依赖
RUN npm install -g @supabase/supabase-js

WORKDIR /app

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev
COPY backend/ ./

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
