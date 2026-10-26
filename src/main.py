from fastapi import FastAPI, HTTPException, Query

from src.config.loader import load_json
from src.services.recommendations import recommend_circles

users = {user["id"]: user for user in load_json("users.json")}
circles = load_json("circles.json")
memberships = load_json("memberships.json")
topics = {topic["slug"]: topic["label"] for topic in load_json("topics.json")}
user_circle_memberships = {
    (membership["user_id"], membership["circle_id"])
    for membership in memberships
}

app = FastAPI(title="Circle Recommendations API")


@app.get("/health")
def check_health():
    return {"status": "ok"}


@app.get("/recommendations")
def get_recommendations(
    user_id: int,
    limit: int = Query(default=5, ge=1, le=10),
):
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_id,
        "recommendations": recommend_circles(
            user=user,
            circles=circles,
            memberships=user_circle_memberships,
            topic_labels=topics,
            limit=limit,
        ),
    }