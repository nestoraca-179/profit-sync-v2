#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="sql-sync-service"

cat <<SERVICE | sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null
[Unit]
Description=SQL Server Synchronizer Service
After=network.target

[Service]
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON_BIN} -m src.main
Restart=always
RestartSec=10
EnvironmentFile=${PROJECT_DIR}/.env

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
