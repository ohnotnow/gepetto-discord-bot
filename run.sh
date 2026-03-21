#!/bin/bash
set -e

# ensure we have one parameter
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <name-of-bot>"
  echo "Example: $0 gepetto"
  echo "(There should be a matching .env.gepetto, for instance)"
  echo ""
  echo "Shared config goes in .env (loaded first, optional)."
  echo "Bot-specific overrides go in .env.<name> (loaded second)."
  exit 1
fi
BOT_NAME=$1

# Create data directories if they don't exist
mkdir -p user_data
mkdir -p data

# Check if the container is already running
if docker ps --format '{{.Names}}' | grep -q "^${BOT_NAME}$"; then
  echo "${BOT_NAME} Container is already running"
  exit 1
fi

#git commit -a -m 'local changes' || echo "No local changes to commit"
git pull origin master --rebase || echo "No remote changes to pull"

docker build -t ${BOT_NAME} .

# Load shared env first (if it exists), then bot-specific overrides.
# Later --env-file values override earlier ones, so .env.${BOT_NAME}
# can selectively replace keys from the base .env.
ENV_FILES=""
if [ -f .env ]; then
  ENV_FILES="--env-file=.env"
fi
ENV_FILES="${ENV_FILES} --env-file=.env.${BOT_NAME}"

docker run --restart=no ${ENV_FILES} -v $(pwd)/stats.json:/app/stats.json -v $(pwd)/user_data:/app/user_data -v $(pwd)/data:/app/data ${BOT_NAME}
