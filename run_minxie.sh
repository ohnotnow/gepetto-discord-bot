#!/bin/bash
set -e

# Create user_data directory if it doesn't exist
mkdir -p user_data

# Check if the container is already running
if docker ps --format '{{.Names}}' | grep -q '^minxie$'; then
  echo "Container is already running"
  exit 1
fi

docker build -t minxie .

# put your various environment variables in a file named .env
docker run --restart=on-failure --env-file=.env -e BOT_PROVIDER=groq -v $(pwd)/random_facts.json:/app/random_facts.json -v $(pwd)/stats.json:/app/stats.json -v $(pwd)/user_data:/app/user_data minxie
