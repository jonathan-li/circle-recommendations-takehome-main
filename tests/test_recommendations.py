import unittest
from datetime import datetime, timezone

from src.config.loader import load_json
from src.services.recommendations import recommend_circles


USERS = {user["id"]: user for user in load_json("users.json")}
CIRCLES = load_json("circles.json")
MEMBERSHIPS = load_json("memberships.json")
TOPIC_LABELS = {
    topic["slug"]: topic["label"] for topic in load_json("topics.json")
}
USER_CIRCLE_MEMBERSHIPS = {
    (membership["user_id"], membership["circle_id"])
    for membership in MEMBERSHIPS
}
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def recommend(user_id: int, limit: int = 10) -> list[dict[str, str | int]]:
    return recommend_circles(
        user=USERS[user_id],
        circles=CIRCLES,
        memberships=USER_CIRCLE_MEMBERSHIPS,
        topic_labels=TOPIC_LABELS,
        limit=limit,
        now=NOW,
    )


class RecommendationTests(unittest.TestCase):
    def test_obvious_matches_rank_before_nonmatches(self):
        results = recommend(7)
        recommended_ids = [result["circle_id"] for result in results]
        self.assertIn(5, recommended_ids)
        self.assertIn(6, recommended_ids)
        self.assertTrue(
            all((7, circle_id) not in USER_CIRCLE_MEMBERSHIPS
                for circle_id in recommended_ids)
        )
        self.assertTrue(
            all(
                "Matches your interest" in result["reason"]
                for result in results[:2]
            )
        )

    def test_duplicate_topics_are_diversified(self):
        results = recommend(15)
        negotiation_ids = {
            10,
            11,
            12,
        }.intersection(result["circle_id"] for result in results)
        self.assertLessEqual(len(negotiation_ids), 2)

    def test_full_and_stale_circles_are_excluded(self):
        results = recommend(23)
        recommended_ids = [result["circle_id"] for result in results]
        self.assertNotIn(20, recommended_ids)
        self.assertNotIn(21, recommended_ids)
        self.assertIn(22, recommended_ids)

    def test_cold_start_gets_general_recommendations(self):
        results = recommend(42)
        self.assertTrue(results)
        self.assertTrue(
            all(
                "Matches your interest" not in result["reason"]
                for result in results
            )
        )

    def test_limit_is_respected(self):
        self.assertEqual(len(recommend(7, limit=3)), 3)

    def test_recommendations_have_the_contract_fields(self):
        self.assertTrue(recommend(7))
        self.assertEqual(
            set(recommend(7)[0]),
            {"circle_id", "name", "reason"},
        )


if __name__ == "__main__":
    unittest.main()
