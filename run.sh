#!/bin/bash
set -e

# Check if the container is already running
if docker ps --format '{{.Names}}' | grep -q '^gepetto$'; then
  echo "Container is already running"
  exit 1
fi

docker build -t gepetto .

docker run --restart=on-failure -e OPENAI_API_KEY="${OPENAI_API_KEY}" -e DISCORD_SERVER_ID="${DISCORD_SERVER_ID}" -e DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" gepetto
