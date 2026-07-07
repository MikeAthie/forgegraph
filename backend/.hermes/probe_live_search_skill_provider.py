from application.services.career_ops_live_search import StdlibCareerOpsLiveSearchProvider

provider = StdlibCareerOpsLiveSearchProvider(timeout_seconds=10)
queries = [
    "site:linkedin.com/jobs Python FastAPI Backend Engineer Spain",
    "site:englishjobs.es/jobs Python Backend Engineer Spain",
    "site:remoterocketship.com Mexico AI Engineer Python remote",
    "site:dailyremote.com remote backend engineer Spain Python",
]
for query in queries:
    print("QUERY", query)
    hits = provider.search(query=query, max_results=3)
    print("hits", len(hits))
    for hit in hits[:3]:
        print("-", hit.get("title"), "|", hit.get("url"), "|", hit.get("snippet"))
