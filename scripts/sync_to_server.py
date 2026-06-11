import paramiko
import os
import sys

host, user, pw = "119.29.16.170", "root", "HONGSHAN@2026!&"
local_base = r"D:/12_其他项目/27_FreeCAD/FreeCADAI_1.0"
remote_base = "/home/app/freecadai"

items = [
    "server/", "deploy/", "scripts/", "web/package.json", "web/tsconfig.json",
    "web/next-env.d.ts", "web/src/",
    "docker-compose.prod.yml", "freecad_ai/", "package.xml", "Init.py", "InitGui.py"
]

exclude_dirs = {"node_modules", ".git", "__pycache__", ".next", "dist"}

def should_skip(name):
    return name in exclude_dirs or name.endswith(".pyc")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, 22, user, pw, timeout=10)
sftp = client.open_sftp()

def ensure_remote_dir(remote_path):
    try:
        sftp.stat(remote_path)
    except:
        parts = remote_path.split("/")
        for i in range(1, len(parts)+1):
            p = "/".join(parts[:i])
            if p:
                try:
                    sftp.stat(p)
                except:
                    sftp.mkdir(p)

def sync_file(local, remote):
    ensure_remote_dir(os.path.dirname(remote))
    sftp.put(local, remote)

def sync_dir(local_dir, remote_dir):
    count = 0
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if not should_skip(d)]
        rel = os.path.relpath(root, local_dir)
        if rel == ".":
            target_dir = remote_dir
        else:
            target_dir = remote_dir + "/" + rel.replace("\\", "/")
        for f in files:
            if f.endswith(".pyc"):
                continue
            local_file = os.path.join(root, f)
            remote_file = target_dir + "/" + f
            ensure_remote_dir(target_dir)
            sftp.put(local_file, remote_file)
            count += 1
    return count

total = 0
for item in items:
    local_path = os.path.join(local_base, item)
    local_path = local_path.replace("\\", "/")
    if item.endswith("/"):
        remote_path = remote_base + "/" + item[:-1]
    else:
        remote_path = remote_base + "/" + item
    if os.path.isdir(local_path):
        c = sync_dir(local_path, remote_path)
        total += c
        print(f"  {item} -> {c} files")
    elif os.path.isfile(local_path):
        sync_file(local_path, remote_path)
        total += 1
        print(f"  {item} -> 1 file")

sftp.close()
client.close()
print(f"\nDone. {total} files synced.")
