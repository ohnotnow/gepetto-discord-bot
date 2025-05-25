import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Directory to store user data files
USER_DATA_DIR = "user_data"

def _ensure_user_data_dir():
    """Ensure the user data directory exists."""
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)

def _get_user_file_path(discord_user_id: str) -> str:
    """Get the file path for a user's data."""
    return os.path.join(USER_DATA_DIR, f"user_{discord_user_id}.json")

def _load_user_data(discord_user_id: str) -> dict:
    """Load user data from file, return empty dict if file doesn't exist."""
    file_path = _get_user_file_path(discord_user_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading user data for {discord_user_id}: {e}")
    return {"information": [], "created_at": None, "last_updated": None}

def _save_user_data(discord_user_id: str, data: dict) -> bool:
    """Save user data to file."""
    _ensure_user_data_dir()
    file_path = _get_user_file_path(discord_user_id)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        logger.error(f"Error saving user data for {discord_user_id}: {e}")
        return False

async def user_information(discord_user_id: str) -> str:
    """
    Retrieves previously stored information about a Discord user to provide context
    for the current interaction.

    Args:
        discord_user_id: The Discord user ID to retrieve information for

    Returns:
        A formatted string containing the user's stored information, or a message
        indicating no information is available
    """
    logger.info(f"Retrieving user information for {discord_user_id}")

    try:
        user_data = _load_user_data(discord_user_id)

        if not user_data.get("information"):
            return "No previously stored information available for this user."

        info_list = user_data["information"]
        last_updated = user_data.get("last_updated", "Unknown")

        # Format the information nicely
        formatted_info = []
        for i, info in enumerate(info_list[-10:], 1):  # Show last 10 entries
            timestamp = info.get("timestamp", "Unknown time")
            content = info.get("content", "")
            formatted_info.append(f"{i}. [{timestamp}] {content}")

        result = f"Stored information for user {discord_user_id}:\n"
        result += "\n".join(formatted_info)
        result += f"\n\nLast updated: {last_updated}"

        return result

    except Exception as e:
        logger.error(f"Error retrieving user information for {discord_user_id}: {e}")
        return "Error retrieving user information."

async def store_user_information(discord_user_id: str, information: str) -> str:
    """
    Stores information about a user interaction that may be useful for future conversations.
    This should be used to remember important facts, preferences, or context about the user.

    Args:
        discord_user_id: The Discord user ID to store information for
        information: The fact, preference, or contextual information about the user

    Returns:
        A confirmation message indicating whether the information was stored successfully
    """
    logger.info(f"Storing user information for {discord_user_id}: {information[:100]}...")

    try:
        user_data = _load_user_data(discord_user_id)

        # Initialize if this is the first time storing data for this user
        if user_data.get("created_at") is None:
            user_data["created_at"] = datetime.now().isoformat()

        # Add the new information with timestamp
        new_info = {
            "content": information,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if "information" not in user_data:
            user_data["information"] = []

        user_data["information"].append(new_info)
        user_data["last_updated"] = datetime.now().isoformat()

        # Keep only the last 50 entries to prevent files from growing too large
        if len(user_data["information"]) > 50:
            user_data["information"] = user_data["information"][-50:]

        # Save the updated data
        if _save_user_data(discord_user_id, user_data):
            return f"Successfully stored information for user {discord_user_id}."
        else:
            return "Error storing user information."

    except Exception as e:
        logger.error(f"Error storing user information for {discord_user_id}: {e}")
        return "Error storing user information."
