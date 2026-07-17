.PHONY: help init init-env init-infra infra backend frontend backend-install frontend-install install \
        wait-db wait-redis status down logs-db logs-redis db-shell redis-shell test

POSTGRES_CONTAINER ?= gokagent-postgres
REDIS_CONTAINER ?= gokagent-redis
POSTGRES_IMAGE ?= postgres:16.13
REDIS_IMAGE ?= redis:7.4
POSTGRES_PORT ?= 5432
REDIS_PORT ?= 6379

export UV_CACHE_DIR := $(CURDIR)/.uv-cache
export UV_PYTHON_INSTALL_DIR := $(CURDIR)/.uv-python

help:                ## 列出常用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============ 一键初始化（首次运行） ============
init: init-env init-infra backend-install frontend-install  ## 首次运行：创建本地配置、启动基础服务、安装前后端依赖
	@echo ""
	@echo "✅ 初始化完成。后续启动打开两个 terminal："
	@echo "   terminal 1: make backend"
	@echo "   terminal 2: make frontend"
	@echo "   前端地址: http://localhost:5173"
	@echo "   后端健康检查: http://localhost:8000/api/health"

init-env:            ## 创建 backend/.env（已存在则不覆盖）
	@if [ ! -f backend/.env ]; then \
		{ \
			echo "APP_SECRET=local-dev-change-me"; \
			echo ""; \
			echo "ANTHROPIC_AUTH_TOKEN=local-dev-token"; \
			echo "ANTHROPIC_BASE_URL=http://localhost:65535"; \
			echo "ANTHROPIC_MODEL=local-dev-model"; \
			echo "ZHIPU_WEB_SEARCH_API_KEY="; \
			echo ""; \
			echo "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:$(POSTGRES_PORT)/gokagent"; \
			echo "REDIS_URL=redis://localhost:$(REDIS_PORT)/0"; \
			echo "TEAM_SPACE_FILE_LOCK_TTL_SECONDS=1800"; \
			echo "TEAM_SPACE_FILE_LOCK_CLEANUP_GRACE_SECONDS=300"; \
			echo ""; \
			echo "WECHAT_WORK_LOGIN_MODE=sso"; \
			echo "WECHAT_WORK_CORP_ID=local-dev-corp"; \
			echo "WECHAT_WORK_AGENT_ID=local-dev-agent"; \
			echo "WECHAT_WORK_SECRET=local-dev-secret"; \
			echo ""; \
			echo "APP_ENV=development"; \
		} > backend/.env; \
		echo "✅ 已创建 backend/.env（本地占位配置，可启动界面；真实 AI/企微能力需后续配置）"; \
	else \
		echo "✅ backend/.env 已存在，跳过创建"; \
	fi

init-infra: infra    ## 启动 PostgreSQL + Redis 并等待可用

# ============ 日常启动 ============
backend: infra       ## 启动后端开发服务器（FastAPI，热更新）
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:            ## 启动前端开发服务器（Vite，热更新）
	cd frontend && npm run dev

infra:               ## 启动 PostgreSQL + Redis（不存在则创建，存在则复用）
	@if docker ps -a --format '{{.Names}}' | grep -qx '$(POSTGRES_CONTAINER)'; then \
		docker start $(POSTGRES_CONTAINER) >/dev/null; \
		echo "✅ PostgreSQL 容器已启动/复用: $(POSTGRES_CONTAINER)"; \
	else \
		docker run -d --name $(POSTGRES_CONTAINER) \
			-e POSTGRES_USER=postgres \
			-e POSTGRES_PASSWORD=postgres \
			-e POSTGRES_DB=gokagent \
			-p $(POSTGRES_PORT):5432 \
			-v gokagent-postgres-data:/var/lib/postgresql/data \
			$(POSTGRES_IMAGE) >/dev/null; \
		echo "✅ PostgreSQL 容器已创建: $(POSTGRES_CONTAINER)"; \
	fi
	@if docker ps -a --format '{{.Names}}' | grep -qx '$(REDIS_CONTAINER)'; then \
		docker start $(REDIS_CONTAINER) >/dev/null; \
		echo "✅ Redis 容器已启动/复用: $(REDIS_CONTAINER)"; \
	else \
		docker run -d --name $(REDIS_CONTAINER) \
			-p $(REDIS_PORT):6379 \
			-v gokagent-redis-data:/data \
			$(REDIS_IMAGE) redis-server --appendonly yes >/dev/null; \
		echo "✅ Redis 容器已创建: $(REDIS_CONTAINER)"; \
	fi
	@$(MAKE) wait-db
	@$(MAKE) wait-redis

# ============ 安装依赖 ============
install: backend-install frontend-install  ## 安装前后端依赖

backend-install:     ## 安装后端依赖（uv，会自动下载 Python 3.13）
	cd backend && uv sync

frontend-install:    ## 安装前端依赖
	cd frontend && npm install

# ============ 基础服务 ============
wait-db:             ## 等待 PostgreSQL 可用
	@echo "等待 PostgreSQL 就绪 ..."
	@for i in $$(seq 1 30); do \
		if docker exec $(POSTGRES_CONTAINER) pg_isready -U postgres >/dev/null 2>&1; then \
			echo "✅ PostgreSQL 已就绪"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "❌ PostgreSQL 启动超时，请执行 make logs-db 查看日志"; \
	exit 1

wait-redis:          ## 等待 Redis 可用
	@echo "等待 Redis 就绪 ..."
	@for i in $$(seq 1 30); do \
		if docker exec $(REDIS_CONTAINER) redis-cli ping >/dev/null 2>&1; then \
			echo "✅ Redis 已就绪"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "❌ Redis 启动超时，请执行 make logs-redis 查看日志"; \
	exit 1

status:              ## 查看基础服务状态
	docker ps --filter name=$(POSTGRES_CONTAINER) --filter name=$(REDIS_CONTAINER)

down:                ## 停止 PostgreSQL + Redis
	-docker stop $(POSTGRES_CONTAINER) $(REDIS_CONTAINER)

logs-db:             ## 查看 PostgreSQL 日志
	docker logs -f $(POSTGRES_CONTAINER)

logs-redis:          ## 查看 Redis 日志
	docker logs -f $(REDIS_CONTAINER)

db-shell:            ## 进入 PostgreSQL shell
	docker exec -it $(POSTGRES_CONTAINER) psql -U postgres -d gokagent

redis-shell:         ## 进入 Redis CLI
	docker exec -it $(REDIS_CONTAINER) redis-cli

# ============ 测试 ============
test:                ## 运行后端测试
	cd backend && uv run pytest
