import requests
import os
import asyncio

class SentryIssue:
    def __init__(self, title, error_type, error_value, tags, user, date_created, stacktrace, breadcrumbs, url):
        self.title = title
        self.error_type = error_type
        self.error_value = error_value
        self.tags = tags
        self.user = user
        self.date_created = date_created
        self.stacktrace = stacktrace
        self.breadcrumbs = breadcrumbs
        self.url = url

def get_sentry_issue(issue_url: str) -> dict:
    issue_id = issue_url.split("/issues/")[1].split("/")[0]
    event_id = "recommended" # see API docs https://docs.sentry.io/api/events/retrieve-an-issue-event/

    response = requests.get(f"https://sentry.io/api/0/issues/{issue_id}/events/{event_id}/", headers={"Authorization": f"Bearer {os.getenv('SENTRY_AUTH_TOKEN')}"})
    response.raise_for_status()
    return response.json()

def parse_sentry_response(api_response: dict, issue_url: str) -> SentryIssue:
    # Extract fields
    title = api_response.get("title", "No title")
    metadata = api_response.get("metadata", {})
    error_type = metadata.get("type", "Unknown")
    error_value = metadata.get("value", "No value provided")

    # Tags
    tags = {tag["key"]: tag["value"] for tag in api_response.get("tags", [])}

    # User info
    user = api_response.get("user", {})
    user_info = {
        "name": user.get("name", "Unknown"),
        "email": user.get("email", "Unknown"),
        "ip_address": user.get("ip_address", "Unknown")
    }

    # Date created
    date_created = api_response.get("dateCreated", "Unknown date")

    # Stacktrace (get top frames)
    stacktrace = []
    entries = api_response.get("entries", [])
    for entry in entries:
        if entry.get("type") == "exception":
            values = entry["data"].get("values", [])
            for value in values:
                frames = value.get("stacktrace", {}).get("frames", [])
                for frame in frames[-3:]:  # Get the last 3 frames (most relevant)
                    stacktrace.append({
                        "filename": frame.get("filename", "Unknown"),
                        "function": frame.get("function", "Unknown"),
                        "lineNo": frame.get("lineNo", "Unknown")
                    })

    # Breadcrumbs
    breadcrumbs = []
    for entry in entries:
        if entry.get("type") == "breadcrumbs":
            breadcrumbs = [
                {
                    "category": crumb.get("category", "Unknown"),
                    "message": crumb.get("message", "No message"),
                    "timestamp": crumb.get("timestamp", "Unknown")
                }
                for crumb in entry.get("data", {}).get("values", [])
            ]

    # Issue URL
    url = issue_url

    return SentryIssue(
        title=title,
        error_type=error_type,
        error_value=error_value,
        tags=tags,
        user=user_info,
        date_created=date_created,
        stacktrace=stacktrace,
        breadcrumbs=breadcrumbs,
        url=url
    )

def format_discord_message(issue: SentryIssue) -> str:
    message = (
        f"**Title**: {issue.title}\n"
        f"**Type**: {issue.error_type}\n"
        f"**Error**: {issue.error_value}\n"
        f"**Environment**: {issue.tags.get('environment', 'Unknown')}\n"
        f"**Browser**: {issue.tags.get('browser', 'Unknown')}\n"
        f"**User**: {issue.user['name']} ({issue.user['email']})\n"
        f"**Created**: {issue.date_created}\n"
        f"**Stacktrace**:\n" +
        "\n".join(
            f"  - {frame['function']} in {frame['filename']}:{frame['lineNo']}"
            for frame in issue.stacktrace
        ) +
        f"\n\n**View More**: [Link]({issue.url})"
    )
    return message


def prepare_data_for_llm(issue: SentryIssue) -> dict:
    # Create a concise dictionary
    data_for_llm = {
        "title": issue.title,
        "error_type": issue.error_type,
        "error_value": issue.error_value,
        "environment": issue.tags.get("environment", "Unknown"),
        "browser": issue.tags.get("browser", "Unknown"),
        "user": {
            "name": issue.user["name"],
            "email": issue.user["email"],
            "ip_address": issue.user["ip_address"]
        },
        "date_created": issue.date_created,
        "stacktrace": [
            f"{frame['function']} in {frame['filename']}:{frame['lineNo']}"
            for frame in issue.stacktrace
        ],
        "breadcrumbs": [
            {
                "category": breadcrumb["category"],
                "message": breadcrumb["message"],
                "timestamp": breadcrumb["timestamp"]
            }
            for breadcrumb in issue.breadcrumbs
        ],
        "culprit": issue.tags.get("culprit", "Unknown"),
        "url": issue.url
    }
    return data_for_llm

def generate_llm_prompt(data: dict) -> str:
    prompt = (
        "Here is an error report from Sentry:\n\n"
        f"**Title**: {data['title']}\n"
        f"**Type**: {data['error_type']}\n"
        f"**Value**: {data['error_value']}\n"
        f"**Environment**: {data['environment']}\n"
        f"**Browser**: {data['browser']}\n"
        f"**User**: {data['user']['name']} ({data['user']['email']})\n"
        f"**Date Created**: {data['date_created']}\n"
        f"**Stacktrace**:\n" +
        "\n".join(data['stacktrace']) +
        f"\n\n**Recent Activity**:\n" +
        "\n".join(
            f"{b['timestamp']}: {b['category']} - {b['message']}"
            for b in data['breadcrumbs']
        ) +
        f"\n\n**Culprit**: {data['culprit']}\n"
        f"**URL**: {data['url']}\n\n"
        "Can you provide targetted, concise insights into what might be causing this issue and suggest debugging steps for an experienced developer?"
    )
    return prompt

def get_sentry_issue_and_parse(issue_url: str) -> tuple[str, str]:
    api_response = get_sentry_issue(issue_url)
    issue = parse_sentry_response(api_response, issue_url)
    data_for_llm = prepare_data_for_llm(issue)
    prompt = generate_llm_prompt(data_for_llm)
    discord_message = format_discord_message(issue)
    return discord_message, prompt

async def process_sentry_issue(url: str) -> tuple[str, str]:
    # use asyncio to run get_sentry_issue_and_parse asynchronysouly and return the results
    return await asyncio.to_thread(get_sentry_issue_and_parse, url)

if __name__ == "__main__":
    url = input("Enter the Sentry issue URL: ")
    discord_message, prompt = get_sentry_issue_and_parse(url)
    print(discord_message)
    print(prompt)
