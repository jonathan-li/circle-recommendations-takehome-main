from datetime import datetime, timedelta, timezone
from typing import Any

INACTIVE_AFTER = timedelta(days=90)
MAX_PER_TOPIC_FIRST_PASS = 2
LEADER_REASON = (
    "You are a designated leader of this Circle — jump in to check recent "
    "member discussions."
)


def _last_activity(circle: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(
        circle["last_activity_at"].replace("Z", "+00:00")
    )


def _is_full(circle: dict[str, Any]) -> bool:
    maximum = circle["max_members"]
    return maximum is not None and circle["member_count"] >= maximum


def _is_inactive(circle: dict[str, Any], now: datetime) -> bool:
    return (
        now - _last_activity(circle) > INACTIVE_AFTER
        and circle["feed_posts_30d"] == 0
        and circle["chat_messages_30d"] <= 5
    )


def _matching_tags(circle: dict[str, Any], interests: set[str]) -> set[str]:
    return set(circle["tags"]).intersection(interests)


def _recent_activity_metrics(
    circles: list[dict[str, Any]],
    activity_records: list[dict[str, Any]],
) -> dict[int, dict[str, int | float]]:
    timestamps = [_last_activity(circle) for circle in circles]
    timestamps.extend(
        datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
        for post in activity_records
    )
    if not timestamps:
        return {
            circle["id"]: {
                "active_member_ratio": 0.0,
                "recent_reactions": 0,
                "recent_comments": 0,
            }
            for circle in circles
        }

    snapshot_at = max(timestamps)
    window_start = snapshot_at - timedelta(days=30)
    active_authors: dict[int, set[int]] = {}
    reactions: dict[int, int] = {}
    comments: dict[int, int] = {}
    for post in activity_records:
        created_at = datetime.fromisoformat(
            post["created_at"].replace("Z", "+00:00")
        )
        if window_start <= created_at <= snapshot_at:
            circle_id = post["circle_id"]
            active_authors.setdefault(circle_id, set()).add(post["author_user_id"])
            reactions[circle_id] = reactions.get(circle_id, 0) + post["reaction_count"]
            comments[circle_id] = comments.get(circle_id, 0) + post["comment_count"]

    return {
        circle["id"]: {
            "active_member_ratio": (
                len(active_authors.get(circle["id"], set())) / circle["member_count"]
                if circle["member_count"] > 0
                else 0.0
            ),
            "recent_reactions": reactions.get(circle["id"], 0),
            "recent_comments": comments.get(circle["id"], 0),
        }
        for circle in circles
    }


def _reason(
    circle: dict[str, Any],
    interests: set[str],
    topic_labels: dict[str, str],
    active_member_ratio: float,
    recent_reactions: int,
    recent_comments: int,
) -> str:
    topic = circle["topic"]
    if topic in interests:
        label = topic_labels.get(topic, topic.replace("-", " "))
        reason = f"Matches your interest in {label.lower()} and has recent activity."
    elif matching_tags := _matching_tags(circle, interests):
        tag = sorted(matching_tags)[0]
        label = topic_labels.get(tag, tag.replace("-", " "))
        reason = (
            f"Related to your interest in {label.lower()} through a Circle tag "
            "and has recent activity."
        )
    else:
        reason = "Trending HOT: a public Circle with recent activity."

    participation = round(active_member_ratio * 100)
    reason += f" {participation}% of members posted in the last 30 days."
    if recent_reactions or recent_comments:
        reaction_label = "reaction" if recent_reactions == 1 else "reactions"
        comment_label = "comment" if recent_comments == 1 else "comments"
        reason += (
            f" Recent posts received {recent_reactions} {reaction_label} and "
            f"{recent_comments} {comment_label}."
        )

    if circle["join_policy"] == "request":
        reason += " You'll need to request to join."
    return reason


def _recommendation(
    circle: dict[str, Any],
    reason: str,
    activity_metrics: dict[int, dict[str, int | float]],
) -> dict[str, Any]:
    return {
        "circle_id": circle["id"],
        "name": circle["name"],
        "active_member_ratio": round(
            float(activity_metrics[circle["id"]]["active_member_ratio"]), 3
        ),
        "reason": reason,
    }


def recommend_circles(
    user: dict[str, Any],
    circles: list[dict[str, Any]],
    memberships: set[tuple[int, int]],
    leader_circle_ids: set[int],
    activity_records: list[dict[str, Any]],
    topic_labels: dict[str, str],
    limit: int = 5,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return eligible Circles ranked by relevance and Circle-level activity."""
    current_time = now or datetime.now(timezone.utc)
    interests = set(user["topic_interests"])
    user_id = user["id"]
    activity_metrics = _recent_activity_metrics(circles, activity_records)
    circles_by_id = {circle["id"]: circle for circle in circles}

    leader_circles = [
        circles_by_id[circle_id]
        for circle_id in leader_circle_ids
        if circle_id in circles_by_id
    ]
    leader_circles.sort(
        key=lambda circle: (
            _last_activity(circle),
            circle["feed_posts_30d"],
            circle["chat_messages_30d"],
            -circle["id"],
        ),
        reverse=True,
    )
    leader_recommendations = [
        _recommendation(circle, LEADER_REASON, activity_metrics)
        for circle in leader_circles[:limit]
    ]
    remaining_limit = limit - len(leader_recommendations)
    if remaining_limit == 0:
        return leader_recommendations

    eligible = [
        circle
        for circle in circles
        if (user_id, circle["id"]) not in memberships
        and circle["id"] not in leader_circle_ids
        and circle["access"] == "public"
        and not _is_full(circle)
        and not _is_inactive(circle, current_time)
    ]
    eligible.sort(
        key=lambda circle: (
            circle["topic"] in interests,
            len(_matching_tags(circle, interests)),
            int(activity_metrics[circle["id"]]["recent_reactions"])
            + int(activity_metrics[circle["id"]]["recent_comments"]),
            _last_activity(circle),
            circle["feed_posts_30d"],
            circle["chat_messages_30d"],
            -circle["id"],
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    topic_counts: dict[str, int] = {}
    for circle in eligible:
        topic = circle["topic"] or f"circle-{circle['id']}"
        if topic_counts.get(topic, 0) >= MAX_PER_TOPIC_FIRST_PASS:
            deferred.append(circle)
            continue

        selected.append(circle)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if len(selected) == remaining_limit:
            break

    if len(selected) < remaining_limit:
        selected_ids = {circle["id"] for circle in selected}
        selected.extend(
            circle for circle in deferred
            if circle["id"] not in selected_ids
        )
        selected = selected[:remaining_limit]

    return leader_recommendations + [
        _recommendation(
            circle,
            _reason(
                circle,
                interests,
                topic_labels,
                float(activity_metrics[circle["id"]]["active_member_ratio"]),
                int(activity_metrics[circle["id"]]["recent_reactions"]),
                int(activity_metrics[circle["id"]]["recent_comments"]),
            ),
            activity_metrics,
        )
        for circle in selected
    ]
