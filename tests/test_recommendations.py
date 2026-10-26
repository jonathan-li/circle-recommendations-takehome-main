import unittest
from datetime import datetime, timezone

from src.config.loader import load_json
from src.services.recommendations import _recent_activity_metrics, recommend_circles


USERS = {user["id"]: user for user in load_json("users.json")}
CIRCLES = load_json("circles.json")
ACTIVITY = load_json("activity.json")
MEMBERSHIPS = load_json("memberships.json")
TOPIC_LABELS = {
    topic["slug"]: topic["label"] for topic in load_json("topics.json")
}
USER_CIRCLE_MEMBERSHIPS = {
    (membership["user_id"], membership["circle_id"])
    for membership in MEMBERSHIPS
}
USER_LEADER_CIRCLES = {
    user_id: {
        membership["circle_id"]
        for membership in MEMBERSHIPS
        if membership["user_id"] == user_id and membership["role"] == "leader"
    }
    for user_id in USERS
}
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def recommend(user_id: int, limit: int = 10) -> list[dict[str, str | int]]:
    return recommend_circles(
        user=USERS[user_id],
        circles=CIRCLES,
        memberships=USER_CIRCLE_MEMBERSHIPS,
        leader_circle_ids=USER_LEADER_CIRCLES[user_id],
        activity_records=ACTIVITY,
        topic_labels=TOPIC_LABELS,
        limit=limit,
        now=NOW,
    )


class RecommendationTests(unittest.TestCase):
    def test_primary_topic_outweighs_tag_match_and_tag_outweighs_no_match(self):
        user = {"id": 500, "topic_interests": ["negotiation"]}
        common = {
            "access": "public",
            "max_members": None,
            "member_count": 1,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }
        circles = [
            {
                **common,
                "id": 1,
                "name": "No match",
                "topic": "confidence",
                "tags": [],
            },
            {
                **common,
                "id": 2,
                "name": "Tag match",
                "topic": "confidence",
                "tags": ["negotiation"],
            },
            {
                **common,
                "id": 3,
                "name": "Primary topic match",
                "topic": "negotiation",
                "tags": [],
            },
        ]

        results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=[],
            topic_labels={
                "negotiation": "Negotiation",
                "confidence": "Confidence",
            },
            limit=3,
            now=NOW,
        )

        self.assertEqual(
            [result["circle_id"] for result in results],
            [3, 2, 1],
        )
        self.assertIn("through a Circle tag", results[1]["reason"])

    def test_leader_circles_are_returned_first_with_exact_reason(self):
        user = {"id": 500, "topic_interests": []}
        leader_circle = {
            "id": 1,
            "name": "My Circle",
            "topic": None,
            "tags": [],
            "access": "unlisted",
            "max_members": 1,
            "member_count": 1,
            "last_activity_at": "2026-06-01T00:00:00Z",
            "feed_posts_30d": 0,
            "chat_messages_30d": 0,
            "join_policy": "request",
        }
        ordinary_circle = {
            **leader_circle,
            "id": 2,
            "name": "Another Circle",
            "access": "public",
            "max_members": None,
            "member_count": 2,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 3,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }

        results = recommend_circles(
            user=user,
            circles=[leader_circle, ordinary_circle],
            memberships={(500, 1)},
            leader_circle_ids={1},
            activity_records=[],
            topic_labels={},
            limit=2,
            now=NOW,
        )

        self.assertEqual([result["circle_id"] for result in results], [1, 2])
        self.assertEqual(
            results[0]["reason"],
            "You are a designated leader of this Circle — jump in to check "
            "recent member discussions.",
        )

    def test_feed_and_chat_counts_do_not_break_ranking_ties(self):
        user = {"id": 500, "topic_interests": []}
        common = {
            "topic": None,
            "tags": [],
            "access": "public",
            "max_members": None,
            "member_count": 1,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "join_policy": "open",
        }
        circles = [
            {
                **common,
                "id": 1,
                "name": "Lower counts",
                "feed_posts_30d": 0,
                "chat_messages_30d": 0,
            },
            {
                **common,
                "id": 2,
                "name": "Higher counts",
                "feed_posts_30d": 10,
                "chat_messages_30d": 20,
            },
        ]

        regular_results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=[],
            topic_labels={},
            limit=2,
            now=NOW,
        )
        leader_results = recommend_circles(
            user=user,
            circles=circles,
            memberships={(500, 1), (500, 2)},
            leader_circle_ids={1, 2},
            activity_records=[],
            topic_labels={},
            limit=2,
            now=NOW,
        )

        self.assertEqual(
            [result["circle_id"] for result in regular_results],
            [1, 2],
        )
        self.assertEqual(
            [result["circle_id"] for result in leader_results],
            [1, 2],
        )

    def test_active_member_ratio_counts_distinct_recent_post_authors(self):
        user = {"id": 500, "topic_interests": []}
        circle = {
            "id": 1,
            "name": "Circle",
            "topic": None,
            "tags": [],
            "access": "public",
            "max_members": None,
            "member_count": 4,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }
        activity_records = [
            {
                "circle_id": 1,
                "author_user_id": 10,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
            {
                "circle_id": 1,
                "author_user_id": 10,
                "created_at": "2026-10-18T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
            {
                "circle_id": 1,
                "author_user_id": 11,
                "created_at": "2026-10-17T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
            {
                "circle_id": 1,
                "author_user_id": 12,
                "created_at": "2026-09-01T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
        ]

        metrics = _recent_activity_metrics([circle], activity_records)
        result = recommend_circles(
            user=user,
            circles=[circle],
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=activity_records,
            topic_labels={},
            limit=1,
            now=NOW,
        )[0]

        self.assertEqual(metrics[1].active_member_ratio, 0.5)
        self.assertIn("High member activity", result["reason"])
        self.assertNotIn("50%", result["reason"])
        self.assertNotIn("active_member_ratio", result)

    def test_high_member_activity_threshold_is_point_four(self):
        user = {"id": 500, "topic_interests": []}
        common = {
            "topic": None,
            "tags": [],
            "access": "public",
            "max_members": None,
            "member_count": 5,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }
        circles = [
            {**common, "id": 1, "name": "At threshold"},
            {**common, "id": 2, "name": "Below threshold"},
        ]
        activity_records = [
            {
                "circle_id": 1,
                "author_user_id": author_id,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            }
            for author_id in (10, 11)
        ] + [
            {
                "circle_id": 2,
                "author_user_id": 20,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            }
        ]

        results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=activity_records,
            topic_labels={},
            limit=2,
            now=NOW,
        )
        by_id = {result["circle_id"]: result for result in results}

        self.assertIn("High member activity", by_id[1]["reason"])
        self.assertNotIn("High member activity", by_id[2]["reason"])

    def test_zero_member_circle_has_zero_active_member_ratio(self):
        user = {"id": 500, "topic_interests": []}
        circle = {
            "id": 1,
            "name": "Circle",
            "topic": None,
            "tags": [],
            "access": "public",
            "max_members": None,
            "member_count": 0,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }

        result = recommend_circles(
            user=user,
            circles=[circle],
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=[
                {
                    "circle_id": 1,
                    "author_user_id": 10,
                    "created_at": "2026-10-19T00:00:00Z",
                    "reaction_count": 0,
                    "comment_count": 0,
                }
            ],
            topic_labels={},
            limit=1,
            now=NOW,
        )[0]

        self.assertNotIn("High member activity", result["reason"])
        self.assertNotIn("active_member_ratio", result)

    def test_active_member_ratio_does_not_change_ranking(self):
        user = {"id": 500, "topic_interests": []}
        common = {
            "topic": None,
            "tags": [],
            "access": "public",
            "max_members": None,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }
        circles = [
            {**common, "id": 1, "name": "Lower participation", "member_count": 4},
            {**common, "id": 2, "name": "Higher participation", "member_count": 4},
        ]
        activity_records = [
            {
                "circle_id": 1,
                "author_user_id": 10,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
            *[
                {
                    "circle_id": 2,
                    "author_user_id": author_id,
                    "created_at": "2026-10-19T00:00:00Z",
                    "reaction_count": 0,
                    "comment_count": 0,
                }
                for author_id in (20, 21, 22)
            ],
        ]

        results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=activity_records,
            topic_labels={},
            limit=2,
            now=NOW,
        )

        self.assertEqual([result["circle_id"] for result in results], [1, 2])
        self.assertNotIn("High member activity", results[0]["reason"])
        self.assertIn("High member activity", results[1]["reason"])

    def test_interest_matches_rank_before_high_engagement_nonmatches(self):
        user = {"id": 500, "topic_interests": ["negotiation"]}
        common = {
            "tags": [],
            "access": "public",
            "max_members": None,
            "member_count": 4,
            "last_activity_at": "2026-10-20T00:00:00Z",
            "feed_posts_30d": 2,
            "chat_messages_30d": 5,
            "join_policy": "open",
        }
        circles = [
            {
                **common,
                "id": 1,
                "name": "Interest match",
                "topic": "negotiation",
            },
            {
                **common,
                "id": 2,
                "name": "High activity nonmatch",
                "topic": "confidence",
            },
            {
                **common,
                "id": 3,
                "name": "Lower activity nonmatch",
                "topic": "resilience",
            },
        ]
        activity_records = [
            {
                "circle_id": 1,
                "author_user_id": 10,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 0,
                "comment_count": 0,
            },
            {
                "circle_id": 2,
                "author_user_id": 20,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 10,
                "comment_count": 8,
            },
            {
                "circle_id": 3,
                "author_user_id": 30,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": 2,
                "comment_count": 1,
            },
            {
                "circle_id": 3,
                "author_user_id": 31,
                "created_at": "2026-09-01T00:00:00Z",
                "reaction_count": 100,
                "comment_count": 100,
            },
        ]

        results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=activity_records,
            topic_labels={"negotiation": "Negotiation"},
            limit=3,
            now=NOW,
        )

        self.assertEqual([result["circle_id"] for result in results], [1, 2, 3])
        self.assertIn("High recent engagement", results[1]["reason"])
        self.assertNotIn("High recent engagement", results[2]["reason"])
        self.assertNotIn("18 reactions", results[1]["reason"])
        self.assertNotIn("Trending", results[1]["reason"])
        self.assertNotIn("High recent engagement", results[0]["reason"])

    def test_high_recent_engagement_marks_top_quartile_only(self):
        user = {"id": 500, "topic_interests": []}
        circles = [
            {
                "id": circle_id,
                "name": f"Circle {circle_id}",
                "topic": None,
                "tags": [],
                "access": "public",
                "max_members": None,
                "member_count": 10,
                "last_activity_at": "2026-10-20T00:00:00Z",
                "feed_posts_30d": 2,
                "chat_messages_30d": 5,
                "join_policy": "open",
            }
            for circle_id in range(1, 5)
        ]
        activity_records = [
            {
                "circle_id": circle_id,
                "author_user_id": circle_id,
                "created_at": "2026-10-19T00:00:00Z",
                "reaction_count": (5 - circle_id) * 10,
                "comment_count": 0,
            }
            for circle_id in range(1, 5)
        ]

        results = recommend_circles(
            user=user,
            circles=circles,
            memberships=set(),
            leader_circle_ids=set(),
            activity_records=activity_records,
            topic_labels={},
            limit=4,
            now=NOW,
        )
        labeled_ids = {
            result["circle_id"]
            for result in results
            if "High recent engagement" in result["reason"]
        }

        self.assertEqual(labeled_ids, {1})
        self.assertTrue(
            all(
                "received" not in result["reason"]
                for result in results
            )
        )

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
                and "Related to your interest" not in result["reason"]
                for result in results
            )
        )

    def test_limit_is_respected(self):
        self.assertEqual(len(recommend(7, limit=3)), 3)

    def test_limit_of_20_is_supported(self):
        self.assertEqual(len(recommend(42, limit=20)), 20)

    def test_recommendations_have_the_contract_fields(self):
        self.assertTrue(recommend(7))
        self.assertEqual(
            set(recommend(7)[0]),
            {"circle_id", "name", "reason"},
        )


if __name__ == "__main__":
    unittest.main()
