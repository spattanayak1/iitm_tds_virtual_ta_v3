import requests
import json
from datetime import datetime, timedelta

# Config - change as needed
DISCOURSE_BASE_URL = "https://discourse.onlinedegree.iitm.ac.in"
CATEGORY_ID = 5  # example category for TDS course (check actual category ID)
START_DATE = "2025-01-01"
END_DATE = "2025-04-14"

def fetch_topics(category_id, page=0):
    url = f"{DISCOURSE_BASE_URL}/c/{category_id}.json?page={page}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def fetch_posts(topic_id):
    url = f"{DISCOURSE_BASE_URL}/t/{topic_id}.json"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def parse_date(date_str):
    # Example: "2025-02-14T18:25:43.000Z"
    return datetime.strptime(date_str[:10], "%Y-%m-%d")

def main():
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end = datetime.strptime(END_DATE, "%Y-%m-%d")

    all_posts = []
    page = 0

    while True:
        data = fetch_topics(CATEGORY_ID, page)
        topics = data.get("topic_list", {}).get("topics", [])
        if not topics:
            break

        for topic in topics:
            created_at = parse_date(topic["created_at"])
            if start <= created_at <= end:
                topic_id = topic["id"]
                post_data = fetch_posts(topic_id)
                posts = post_data.get("post_stream", {}).get("posts", [])
                for post in posts:
                    post_date = parse_date(post["created_at"])
                    if start <= post_date <= end:
                        all_posts.append({
                            "topic_id": topic_id,
                            "topic_title": topic["title"],
                            "post_id": post["id"],
                            "post_number": post["post_number"],
                            "username": post["username"],
                            "created_at": post["created_at"],
                            "cooked": post["cooked"],  # HTML content
                            "raw": post.get("raw", "")
                        })

        page += 1

    # Save all posts to JSON
    with open("discourse_posts.json", "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(all_posts)} posts to discourse_posts.json")

if __name__ == "__main__":
    main()
