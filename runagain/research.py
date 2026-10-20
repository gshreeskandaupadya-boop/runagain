import os, requests

def search(query: str, n: int = 5) -> list[dict]:
    """Runtime Tavily call. Returns [{title,url,content}] for the evidence panel."""
    r = requests.post("https://api.tavily.com/search",
                      headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                      json={"query": query, "max_results": n}, timeout=60)
    r.raise_for_status()
    return [{"title": x.get("title"), "url": x.get("url"), "content": (x.get("content") or "")[:800]}
            for x in r.json().get("results", [])]
