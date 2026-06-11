#!/usr/bin/env python3
"""
开发阶段快速部署 — 仅同步代码到服务器容器，跳过全量 Docker 镜像构建。

用法:
  python scripts/dev_deploy.py           # 仅后端 Python 变更（docker cp + 重启，~15秒）
  python scripts/dev_deploy.py --web     # 后端 + 前端同步（含 Web 镜像构建，~2分钟）

完整部署（含全量镜像构建）请用 sync_and_deploy.ps1。
"""

import paramiko
import os
import sys
import time

SERVER = "119.29.16.170"
USER = "root"
PASSWORD = "HONGSHAN@2026!&"
REMOTE_BASE = "/home/app/freecadai"
LOCAL_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 后端 Python 文件（可直接 docker cp 热替换）
BACKEND_ITEMS = [
    "server/",
    "freecad_ai/",
]

# 前端文件（需要重新构建镜像）
FRONTEND_ITEMS = [
    "web/src/",
    "web/package.json",
    "web/package-lock.json",
    "web/tsconfig.json",
    "web/next.config.mjs",
]

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist"}


def ensure_dir(sftp, path):
    try:
        sftp.stat(path)
    except:
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            p = "/".join(parts[:i])
            if p:
                try:
                    sftp.stat(p)
                except:
                    sftp.mkdir(p)


def sync_items(sftp, items):
    """增量同步指定列表的文件到服务器"""
    total = 0
    for item in items:
        local_path = os.path.join(LOCAL_BASE, item).replace("\\", "/")
        remote_path = f"{REMOTE_BASE}/{item}"
        if remote_path.endswith("/"):
            remote_path = remote_path[:-1]

        if os.path.isdir(local_path):
            for root, dirs, files in os.walk(local_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                rel = os.path.relpath(root, local_path)
                target = remote_path if rel == "." else f"{remote_path}/{rel.replace(chr(92), '/')}"
                for f in files:
                    if f.endswith(".pyc"):
                        continue
                    lf = os.path.join(root, f)
                    rf = f"{target}/{f}"
                    ensure_dir(sftp, target)
                    sftp.put(lf, rf)
                    total += 1
        elif os.path.isfile(local_path):
            ensure_dir(sftp, os.path.dirname(remote_path))
            sftp.put(local_path, remote_path)
            total += 1
    return total


def exec_remote(client, cmd, timeout=30):
    """在远程服务器执行命令并返回输出"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print(f"  STDERR: {err[:300]}")
    return out


def update_backend(client):
    """docker cp 后端代码到容器 + 重启（无需构建镜像）"""
    print("\n--- 后端热更新 ---")
    for svc in ["api", "worker"]:
        container = f"freecadai-{svc}"
        print(f"  cp -> {container}...")
        exec_remote(client, f"docker cp {REMOTE_BASE}/server/. {container}:/app/server/ 2>&1", timeout=10)
        exec_remote(client, f"docker cp {REMOTE_BASE}/freecad_ai/. {container}:/app/freecad_ai/ 2>&1", timeout=10)

    print("  重启 api / worker...")
    exec_remote(client, "docker restart freecadai-api freecadai-worker 2>&1", timeout=30)
    print("  后端更新完成。")


def update_frontend(client):
    """重新构建前端镜像（源码有变动时用，比全量构建快）"""
    print("\n--- 前端重新构建 ---")
    print("  构建 web 镜像...")
    result = exec_remote(client,
        "cd /home/app/freecadai && docker compose -f docker-compose.prod.yml build web 2>&1",
        timeout=300)
    # 只打印关键行
    for line in result.split("\n"):
        if any(k in line for k in ["DONE", "ERROR", "error", "failed", "Success", "exporting", "Compiled"]):
            print(f"  {line.strip()[:120]}")

    print("  启动 web...")
    exec_remote(client,
        "cd /home/app/freecadai && docker compose -f docker-compose.prod.yml up -d web 2>&1", timeout=60)
    print("  前端更新完成。")


def health_check(client):
    """检查服务状态"""
    print("\n--- 健康检查 ---")
    time.sleep(3)
    result = exec_remote(client, "curl -s http://localhost:8000/health 2>&1", timeout=10)
    print(f"  API: {result.strip()}")

    containers = exec_remote(client,
        "docker ps --filter name=freecadai --format 'table {{.Names}}\t{{.Status}}'", timeout=10)
    print(f"  容器:\n{containers}")


def main():
    rebuild_web = "--web" in sys.argv

    print("=" * 50)
    print("  FreeCADAI 开发快速部署")
    if rebuild_web:
        print("  模式: 后端热更新 + 前端重构")
    else:
        print("  模式: 仅后端热更新（前端用 --web）")
    print("=" * 50)

    # 连接服务器
    print("\n[1/4] 连接服务器...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER, 22, USER, PASSWORD, timeout=10)
    sftp = client.open_sftp()

    # 同步代码
    print("[2/4] 同步代码到服务器...")
    all_items = list(BACKEND_ITEMS)
    if rebuild_web:
        all_items.extend(FRONTEND_ITEMS)
    count = sync_items(sftp, all_items)
    print(f"      已同步 {count} 个文件")

    sftp.close()

    # 更新服务
    print("[3/4] 更新服务...")
    update_backend(client)
    if rebuild_web:
        update_frontend(client)

    # 健康检查
    print("[4/4] 健康检查...")
    health_check(client)

    client.close()
    print("\n=== 部署完成！ ===")


if __name__ == "__main__":
    main()
