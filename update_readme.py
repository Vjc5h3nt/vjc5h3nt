import os
import re
from datetime import datetime, timezone

import httpx

# Configuration
GITHUB_USERNAME = "Vjc5h3nt"
README_FILE = "README.md"
MAX_RECENT_PRS = 8

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

GRAPHQL_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    pullRequests(first: 50, states: [OPEN, CLOSED, MERGED], orderBy: {field: CREATED_AT, direction: DESC}, after: $after) {
      totalCount
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        title
        url
        state
        createdAt
        mergedAt
        repository {
          nameWithOwner
          name
          url
          owner {
            login
          }
        }
      }
    }
  }
}
"""


def replace_chunk(content: str, marker: str, chunk: str) -> str:
    pattern = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    replacement = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(marker, chunk, marker)
    return pattern.sub(replacement, content)


def fetch_prs(token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    all_prs = []
    has_next_page = True
    after_cursor = None
    total_count = 0

    while has_next_page:
        variables = {"login": GITHUB_USERNAME}
        if after_cursor:
            variables["after"] = after_cursor

        response = httpx.post(
            GITHUB_GRAPHQL_URL,
            json={"query": GRAPHQL_QUERY, "variables": variables},
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")

        pr_data = data["data"]["user"]["pullRequests"]
        total_count = pr_data["totalCount"]
        all_prs.extend(pr_data["nodes"])

        has_next_page = pr_data["pageInfo"]["hasNextPage"]
        after_cursor = pr_data["pageInfo"]["endCursor"]

    return {"prs": all_prs, "total_count": total_count}


def get_status_emoji(state: str) -> str:
    return {
        "OPEN": "🟡 Open",
        "MERGED": "🟢 Merged",
        "CLOSED": "🔴 Closed",
    }.get(state, state)


def truncate_title(title: str, max_length: int = 45) -> str:
    if len(title) <= max_length:
        return title
    return title[: max_length - 3] + "..."


def filter_external_prs(prs: list) -> list:
    return [
        pr
        for pr in prs
        if pr["repository"]["owner"]["login"].lower() != GITHUB_USERNAME.lower()
    ]


def generate_recent_prs_table(prs: list, limit: int = MAX_RECENT_PRS) -> str:
    external_prs = filter_external_prs(prs)[:limit]

    if not external_prs:
        return "No recent external contributions yet."

    lines = [
        "| Repository | PR | Status |",
        "|------------|----|----|",
    ]

    for pr in external_prs:
        repo = pr["repository"]
        repo_link = f"[{repo['nameWithOwner']}]({repo['url']})"
        pr_title = truncate_title(pr["title"])
        pr_link = f"[{pr_title}]({pr['url']})"
        status = get_status_emoji(pr["state"])
        lines.append(f"| {repo_link} | {pr_link} | {status} |")

    return "\n".join(lines)


def generate_contribution_summary(prs: list, total_count: int) -> str:
    external_prs = filter_external_prs(prs)

    by_org = {}
    for pr in external_prs:
        owner = pr["repository"]["owner"]["login"]
        repo = pr["repository"]["name"]
        if owner not in by_org:
            by_org[owner] = {"repos": set(), "count": 0}
        by_org[owner]["repos"].add(repo)
        by_org[owner]["count"] += 1

    lines = [
        f"**Total Pull Requests:** {total_count}",
        "",
        "| Project | Contributions |",
        "|---------|---------------|",
    ]

    sorted_orgs = sorted(by_org.items(), key=lambda x: x[1]["count"], reverse=True)

    for org, data in sorted_orgs:
        repos = ", ".join(sorted(data["repos"]))
        lines.append(f"| {org} | {data['count']} PRs ({repos}) |")

    return "\n".join(lines)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        try:
            import subprocess

            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True
            )
            if result.returncode == 0:
                token = result.stdout.strip()
        except Exception:
            pass

    if not token:
        raise ValueError("GITHUB_TOKEN environment variable required")

    print(f"Fetching PRs for {GITHUB_USERNAME}...")
    data = fetch_prs(token)

    prs = data["prs"]
    total_count = data["total_count"]
    external_prs = filter_external_prs(prs)

    print(f"Found {total_count} total PRs")
    print(f"External contributions: {len(external_prs)}")

    with open(README_FILE, "r") as f:
        readme_content = f.read()

    recent_prs_md = generate_recent_prs_table(prs)
    all_prs_md = generate_contribution_summary(prs, total_count)

    updated_content = replace_chunk(readme_content, "OPEN_PRS", recent_prs_md)
    updated_content = replace_chunk(updated_content, "ALL_PRS", all_prs_md)

    with open(README_FILE, "w") as f:
        f.write(updated_content)

    print("README.md updated successfully!")
    print(f"Recent PRs shown: {min(len(external_prs), MAX_RECENT_PRS)}")
    print(f"Last updated: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
