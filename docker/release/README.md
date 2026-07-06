# Release 镜像打包说明

这套配置用于客户 Linux 服务器 Docker 部署场景。现有 `docker/Dockerfile` 和 `docker/docker-compose.yml` 保持开发/常规部署用途不变。

## 内部构建镜像

先构建后端基础镜像:

```bash
docker build -f docker/Dockerfile_base -t gokagent-backend:base .
```

再构建 release 镜像:

```bash
docker build -f docker/Dockerfile.release -t gokagent-backend:release .
```

如需推送私有镜像仓库:

```bash
docker tag gokagent-backend:release registry.example.com/gokagent/backend:1.0.0
docker push registry.example.com/gokagent/backend:1.0.0
```

如需离线交付:

```bash
docker save gokagent-backend:release -o gokagent-backend-release.tar
```

## 客户侧部署

客户服务器只需要:

- `docker-compose.release.yml`
- `.env`
- 私有仓库访问权限,或离线镜像 tar

使用私有仓库时:

```bash
GOKAGENT_IMAGE=registry.example.com/gokagent/backend:1.0.0 \
docker compose -f docker-compose.release.yml up -d
```

使用离线镜像时:

```bash
docker load -i gokagent-backend-release.tar
docker compose -f docker-compose.release.yml up -d
```

## 源码保护边界

最终 release 镜像不复制 `backend/app` 源码目录,业务后端包由 Nuitka 编译成扩展模块后启动。镜像会保留运行所需的 Python 三方依赖虚拟环境。前端按当前 Vite 构建产物交付,不做额外混淆压缩。
