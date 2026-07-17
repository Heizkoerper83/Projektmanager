#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${PMTOOL_SERVICE_NAME:-pmtool.service}"

sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
