#!/usr/bin/env python3
"""Fetch complete GitHub contribution history via gh CLI and GraphQL API."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path.home() / ".gitgud" / "contributions.json"


def gh_graphql(query: str, variables: dict) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, val in variables.items():
        cmd.extend(["-f", f"{key}={val}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gh error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    if "errors" in data:
        print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)
    return data


def gh_rest(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", endpoint], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

MAIN_QUERY = """
query($user: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
      restrictedContributionsCount
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate }
        contributions(first: 100) {
          totalCount
          nodes { occurredAt commitCount }
          pageInfo { hasNextPage endCursor }
        }
      }
      issueContributions(first: 100) {
        totalCount
        nodes {
          occurredAt isRestricted
          issue { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
      pullRequestContributions(first: 100) {
        totalCount
        nodes {
          occurredAt isRestricted
          pullRequest { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
      pullRequestReviewContributions(first: 100) {
        totalCount
        nodes {
          occurredAt isRestricted
          pullRequestReview { state }
          pullRequest { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
      repositoryContributions(first: 100) {
        totalCount
        nodes {
          occurredAt isRestricted
          repository { nameWithOwner isPrivate url }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PAGE_QUERIES = {
    "issueContributions": """
query($user: String!, $from: DateTime!, $to: DateTime!, $after: String!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      issueContributions(first: 100, after: $after) {
        nodes {
          occurredAt isRestricted
          issue { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""",
    "pullRequestContributions": """
query($user: String!, $from: DateTime!, $to: DateTime!, $after: String!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      pullRequestContributions(first: 100, after: $after) {
        nodes {
          occurredAt isRestricted
          pullRequest { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""",
    "pullRequestReviewContributions": """
query($user: String!, $from: DateTime!, $to: DateTime!, $after: String!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      pullRequestReviewContributions(first: 100, after: $after) {
        nodes {
          occurredAt isRestricted
          pullRequestReview { state }
          pullRequest { title number url repository { nameWithOwner } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""",
    "repositoryContributions": """
query($user: String!, $from: DateTime!, $to: DateTime!, $after: String!) {
  user(login: $user) {
    contributionsCollection(from: $from, to: $to) {
      repositoryContributions(first: 100, after: $after) {
        nodes {
          occurredAt isRestricted
          repository { nameWithOwner isPrivate url }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""",
}


def paginate(connection_name: str, username: str, from_date: str, to_date: str, cursor: str) -> list:
    """Fetch remaining pages for a flat contribution connection."""
    all_nodes = []
    query = PAGE_QUERIES[connection_name]
    while True:
        data = gh_graphql(query, {
            "user": username, "from": from_date, "to": to_date, "after": cursor,
        })
        connection = data["data"]["user"]["contributionsCollection"][connection_name]
        all_nodes.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    return all_nodes


def main():
    user_info = gh_rest("user")
    username = user_info["login"]
    created_at = user_info["created_at"]
    start_year = int(created_at[:4])
    now = datetime.now(timezone.utc)
    now_year = now.year
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Fetching contribution history for {username} ({start_year}\u2013{now_year})...")

    years = []

    for year in range(start_year, now_year + 1):
        from_date = created_at if year == start_year else f"{year}-01-01T00:00:00Z"
        to_date = fetched_at if year == now_year else f"{year}-12-31T23:59:59Z"

        print(f"  {year}...", end="", flush=True)

        data = gh_graphql(MAIN_QUERY, {"user": username, "from": from_date, "to": to_date})
        cc = data["data"]["user"]["contributionsCollection"]

        # Flatten calendar weeks into day list
        calendar = [
            day
            for week in cc["contributionCalendar"]["weeks"]
            for day in week["contributionDays"]
        ]

        totals = {
            "contributions": cc["contributionCalendar"]["totalContributions"],
            "commits": cc["totalCommitContributions"],
            "issues": cc["totalIssueContributions"],
            "pullRequests": cc["totalPullRequestContributions"],
            "pullRequestReviews": cc["totalPullRequestReviewContributions"],
            "repositories": cc["totalRepositoryContributions"],
            "restricted": cc["restrictedContributionsCount"],
        }

        # Commit contributions by repo (nested pagination not pursued — flagged)
        commits = []
        for entry in cc["commitContributionsByRepository"]:
            commits.append({
                "repository": entry["repository"]["nameWithOwner"],
                "isPrivate": entry["repository"]["isPrivate"],
                "totalCount": entry["contributions"]["totalCount"],
                "truncated": entry["contributions"]["pageInfo"]["hasNextPage"],
                "days": [
                    {"date": n["occurredAt"], "commits": n["commitCount"]}
                    for n in entry["contributions"]["nodes"]
                ],
            })

        # Flat contribution types — paginate if needed
        type_data = {}
        for conn in PAGE_QUERIES:
            connection = cc[conn]
            nodes = list(connection["nodes"])
            if connection["pageInfo"]["hasNextPage"]:
                print(f" +{conn}", end="", flush=True)
                cursor = connection["pageInfo"]["endCursor"]
                nodes.extend(paginate(conn, username, from_date, to_date, cursor))
            type_data[conn] = nodes

        years.append({
            "year": year,
            "from": from_date,
            "to": to_date,
            "totals": totals,
            "calendar": calendar,
            "commits": commits,
            "issues": type_data["issueContributions"],
            "pullRequests": type_data["pullRequestContributions"],
            "pullRequestReviews": type_data["pullRequestReviewContributions"],
            "repositoriesCreated": type_data["repositoryContributions"],
        })
        print(" done")

    output = {"user": username, "fetched_at": fetched_at, "years": years}
    OUT.write_text(json.dumps(output, indent=2))

    size = OUT.stat().st_size
    total_days = sum(len(y["calendar"]) for y in years)
    total_contribs = sum(y["totals"]["contributions"] for y in years)
    print(f"\nSaved to {OUT}")
    print(f"Size: {size / 1000:.1f} KB")
    print(f"Years: {len(years)} | Calendar days: {total_days} | Total contributions: {total_contribs}")


if __name__ == "__main__":
    main()
