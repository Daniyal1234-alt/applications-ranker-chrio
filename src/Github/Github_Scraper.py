import requests
from datetime import datetime
import os
from dotenv import load_dotenv
import re
import requests
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

def get_github_contributions(username):
    query = """
    query($username: String!) {
        user(login: $username) {
            contributionsCollection {
                contributionCalendar {
                    totalContributions
                    weeks {
                        contributionDays {
                            date
                            contributionCount
                        }
                    }
                }
            }
        }
    }
    """

    url = "https://api.github.com/graphql"

    headers = {
        "Authorization": "bearer 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",
        "Content-Type": "application/json",
    }

    variables = {"username": username}

    try:
        response = requests.post(
            url, json={"query": query, "variables": variables}, headers=headers
        )
        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            return {"error": data["errors"][0]["message"]}

        contributions = data["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]

        total_contributions = contributions["totalContributions"]
        # contribution_days = []

        # for week in contributions["weeks"]:
        #     for day in week["contributionDays"]:
        #         contribution_days.append(
        #             {"date": day["date"], "count": day["contributionCount"]}
        #         )

        return {
            "total_contributions": total_contributions,
            # "contributions": contribution_days,
        }

    except requests.RequestException as e:
        return {"error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}


def format_date(date_str):
    """Format ISO date string to a more readable format"""
    if not date_str:
        return None
    date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    return date_obj.strftime("%B %d, %Y at %I:%M %p")


def get_repository_info(username, token):
    """
    Get detailed information about all repositories for a given GitHub username.

    Args:
        username (str): GitHub username
        token (str): GitHub personal access token

    Returns:
        list: List of dictionaries containing repository information
    """
    # GraphQL query to get repository data
    query = """
    query($username: String!, $first: Int!) {
        user(login: $username) {
            repositories(first: $first, orderBy: {field: UPDATED_AT, direction: DESC}) {
                nodes {
                    name
                    description
                    url
                    stargazerCount
                    forkCount
                    watchers {
                        totalCount
                    }
                    languages(first: 10) {
                        nodes {
                            name
                        }
                        totalCount
                    }
                    createdAt
                    updatedAt
                    isFork
                    readme: object(expression: "HEAD:README.md") {
                        ... on Blob {
                            text
                        }
                    }
                    repositoryTopics(first: 10) {
                        nodes {
                            topic {
                                name
                            }
                        }
                    }
                    openIssues: issues(states: OPEN) {
                        totalCount
                    }
                    closedIssues: issues(states: CLOSED) {
                        totalCount
                    }
                    openPullRequests: pullRequests(states: OPEN) {
                        totalCount
                    }
                    mergedPullRequests: pullRequests(states: MERGED) {
                        totalCount
                    }
                }
            }
        }
    }
    """

    # GitHub GraphQL API endpoint
    url = "https://api.github.com/graphql"

    # Headers for the request
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
    }

    # Variables for the query
    variables = {"username": username, "first": 100}  # Number of repositories to fetch

    try:
        # Make the request
        response = requests.post(
            url, json={"query": query, "variables": variables}, headers=headers
        )
        response.raise_for_status()

        # Parse the response
        data = response.json()

        if "errors" in data:
            return {"error": data["errors"][0]["message"]}

        # Check if user exists
        if not data["data"]["user"]:
            return {"error": f"User {username} not found"}

        # Extract repository data
        repositories = data["data"]["user"]["repositories"]["nodes"]

        if not repositories:
            return {"error": f"No repositories found for user {username}"}

        # Process each repository
        repo_info = []
        for repo in repositories:
            # Extract languages
            languages = [lang["name"] for lang in repo["languages"]["nodes"]]

            # Extract topics
            topics = [
                topic["topic"]["name"] for topic in repo["repositoryTopics"]["nodes"]
            ]

            # Create repository info dictionary
            repo_data = {
                "name": repo["name"],
                "description": repo["description"],
                "url": repo["url"],
                "stars": repo["stargazerCount"],
                "forks": repo["forkCount"],
                "watchers": repo["watchers"]["totalCount"],
                "languages": languages,
                "languages_count": repo["languages"]["totalCount"],
                "created_at": format_date(repo["createdAt"]),
                "updated_at": format_date(repo["updatedAt"]),
                "is_fork": repo["isFork"],
                "topics": topics,
                "open_issues": repo["openIssues"]["totalCount"],
                "closed_issues": repo["closedIssues"]["totalCount"],
                "open_pull_requests": repo["openPullRequests"]["totalCount"],
                "merged_pull_requests": repo["mergedPullRequests"]["totalCount"],
                "has_readme": bool(repo["readme"]),
                "readme_content": repo["readme"]["text"] if repo["readme"] else None,
            }

            repo_info.append(repo_data)

        return repo_info

    except requests.RequestException as e:
        return {"error": f"Failed to fetch data: {str(e)}"}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}
    
def extract_username(url):
    match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([^/?#]+)", url)
    return match.group(1) if match else None

def scrape_github_profile (applicant_id, url):
    username = extract_username(url)
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not found in .env file")
        print("Please make sure you have a .env file with GITHUB_TOKEN=your_token_here")
        exit(1)

    contribution_result = get_github_contributions(username)
    repo_result = get_repository_info(username, token)
    data = {
        "id": applicant_id,
        "source": "github",
        "data": [contribution_result, repo_result]
    }
    return data


# if __name__ == "__main__":
#     # Get GitHub token from .env file
#     token = os.getenv("GITHUB_TOKEN")
#     if not token:
#         print("Error: GITHUB_TOKEN not found in .env file")
#         print("Please make sure you have a .env file with GITHUB_TOKEN=your_token_here")
#         exit(1)

#     username = "ghausdev"

#     # Get contribution data
#     contribution_result = get_github_contributions(username)
#     print("\nContribution Data:")
#     print(contribution_result)

#     # Get repository data
#     repo_result = get_repository_info(username, token)

#     # Check if repo_result is an error
#     if isinstance(repo_result, dict) and "error" in repo_result:
#         print(f"\nError fetching repository data: {repo_result['error']}")
#     else:
#         print("\nRepository Data:")
#         for repo in repo_result:
#             print(f"\nRepository: {repo['name']}")
#             print(f"Description: {repo['description']}")
#             print(f"URL: {repo['url']}")
#             print(f"Stars: {repo['stars']}")
#             print(f"Forks: {repo['forks']}")
#             print(f"Watchers: {repo['watchers']}")
#             print(
#                 f"Languages ({repo['languages_count']}): {', '.join(repo['languages'])}"
#             )
#             print(f"Created: {repo['created_at']}")
#             print(f"Last Updated: {repo['updated_at']}")
#             print(f"Topics: {', '.join(repo['topics'])}")
#             print(f"Open Issues: {repo['open_issues']}")
#             print(f"Closed Issues: {repo['closed_issues']}")
#             print(f"Open PRs: {repo['open_pull_requests']}")
#             print(f"Merged PRs: {repo['merged_pull_requests']}")
#             print(f"Has README: {repo['has_readme']}")
#             print("-" * 50)
