#!/bin/bash
set -e

# Check if the container is already running
if docker ps --format '{{.Names}}' | grep -q '^gepetto$'; then
  echo "Container is already running"
  exit 1
fi

docker build -t gepetto .

docker run --restart=on-failure -p 8000:8000 -e OPENAI_API_KEY="${OPENAI_API_KEY}" -e DISCORD_API_KEY="${DISCORD_API_KEY}" gepetto
