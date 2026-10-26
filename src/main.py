from fastapi import FastAPI
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_json(filename: str):
    data_file_path = DATA_DIR / filename
    with open(data_file_path, "r", encoding="utf-8") as f:
        return json.load(f)

users = load_json("users.json")
topics = load_json("topics.json")
memberships = load_json("memberships.json")
circles = load_json("circles.json")
activity = load_json("activity.json")

user_circle_memberships = set(
    (m["user_id"], m["circle_id"]) for m in memberships
)
def is_already_member(user_id: int, circle_id: int, memberships_set) -> bool:
    return (user_id, circle_id) in memberships_set
app = FastAPI()

@app.get("/health") #Testing APP works
async def check_health():
    return {"status": "ok"}

@app.get("/recommendations")
async def get_recommendations(user_id: int, limit: int = 5):
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return {"error": "User not found"}
    
    return {
        "user_id": user["id"],
        "recommendations": 
            [(c["id"], c["name"]) for c in circles if c["topic"] in user["topic_interests"] 
             and is_already_member(user["id"], c["id"], user_circle_memberships) is False][:limit]
    }    