#ssh-keygen -t ed25519 -f C:\Users\Administrator\.ssh\id_ed25519 -N ""
#type C:\Users\Administrator\.ssh\id_ed25519.pub | ssh root@119.29.16.170 "cat >> ~/.ssh/authorized_keys"
#.\scripts\sync_and_deploy.ps1

#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$Server = "root@119.29.16.170"
$RemoteDir = "/home/app/freecadai"

Write-Host "=== Syncing code to server ===" -ForegroundColor Green

# Sync only source files, skip large dirs
scp -r `
  docker-compose.prod.yml `
  server `
  web/src `
  web/package.json `
  web/package-lock.json `
  web/next.config.mjs `
  web/tsconfig.json `
  web/Dockerfile `
  web/Dockerfile.prebuilt `
  web/public `
  scripts/deploy_on_server.sh `
  freecad_ai `
  Init.py `
  InitGui.py `
  package.xml `
  "${Server}:${RemoteDir}/"

Write-Host "=== Running deploy on server ===" -ForegroundColor Green
ssh $Server "bash ${RemoteDir}/scripts/deploy_on_server.sh"
