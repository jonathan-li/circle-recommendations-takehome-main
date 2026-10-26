from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

INACTIVE_AFTER = timedelta(days=90)
MAX_PER_TOPIC_FIRST_PASS = 2
HIGH_MEMBER_ACTIVITY_RATIO = 0.4
LEADER_REASON = (
    "You are a designated leader of this Circle — jump in to check recent "
    "member discussions."
)


@dataclass(frozen=True)
class ActivityMetrics:
    active_member_ratio: float = 0.0
    recent_reactions: int = 0
    recent_comments: int = 0


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _last_activity(circle: dict[str, Any]) -> datetime:
    return _parse_datetime(circle["last_activity_at"])


def _is_full(circle: dict[str, Any]) -> bool:
    maximum = circle["max_members"]
    return maximum is not None and circle["member_count"] >= maximum


def _is_inactive(circle: dict[str, Any], now: datetime) -> bool:
    return (
        now - _last_activity(circle) > INACTIVE_AFTER
        and circle["feed_posts_30d"] <= 0
        and circle["chat_messages_30d"] <= 5
    )


def _matching_tags(circle: dict[str, Any], interests: set[str]) -> set[str]:
    return set(circle["tags"]).intersection(interests)


def _recent_activity_metrics(
    circles: list[dict[str, Any]],
    activity_records: list[dict[str, Any]],
) -> dict[int, ActivityMetrics]:
    timestamps = [_last_activity(circle) for circle in circles]
    timestamps.extend(_parse_datetime(post["created_at"]) for post in activity_records)
    if not timestamps:
        return {circle["id"]: ActivityMetrics() for circle in circles}

    window_end = max(timestamps)
    window_start = window_end - timedelta(days=30)
    active_authors: dict[int, set[int]] = {}
    reactions: dict[int, int] = {}
    comments: dict[int, int] = {}

    for post in activity_records:
        if not window_start <= _parse_datetime(post["created_at"]) <= window_end:
            continue

        circle_id = post["circle_id"]
        active_authors.setdefault(circle_id, set()).add(post["author_user_id"])
        reactions[circle_id] = reactions.get(circle_id, 0) + post["reaction_count"]
        comments[circle_id] = comments.get(circle_id, 0) + post["comment_count"]

    return {
        circle["id"]: ActivityMetrics(
            active_member_ratio=(
                len(active_authors.get(circle["id"], set())) / circle["member_count"]
                if circle["member_count"] > 0
                else 0.0
            ),
            recent_reactions=reactions.get(circle["id"], 0),
            recent_comments=comments.get(circle["id"], 0),
        )
        for circle in circles
    }


def _reason(
    circle: dict[str, Any],
    interests: set[str],
    topic_labels: dict[str, str],
    activity: ActivityMetrics,
    high_recent_engagement: bool,
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
        reason = "A public Circle with recent activity."

    if activity.active_member_ratio >= HIGH_MEMBER_ACTIVITY_RATIO:
        reason += " High member activity."
    if high_recent_engagement:
        reason += " High recent engagement."

    if circle["join_policy"] == "request":
        reason += " You'll need to request to join."
    return reason


def _high_engagement_circle_ids(
    circles: list[dict[str, Any]],
    activity_by_circle: dict[int, ActivityMetrics],
) -> set[int]:
    scores = {
        circle["id"]: (
            activity_by_circle[circle["id"]].recent_reactions
            + activity_by_circle[circle["id"]].recent_comments
        )
        for circle in circles
    }
    positive_scores = sorted(
        (score for score in scores.values() if score > 0),
        reverse=True,
    )
    if not positive_scores:
        return set()

    top_quartile_size = ceil(len(circles) * 0.25)
    threshold = positive_scores[min(top_quartile_size, len(positive_scores)) - 1]
    return {
        circle_id
        for circle_id, score in scores.items()
        if score >= threshold and score > 0
    }


def _recommendation(
    circle: dict[str, Any],
    reason: str,
) -> dict[str, str | int]:
    return {
        "circle_id": circle["id"],
        "name": circle["name"],
        "reason": reason,
    }


def _select_diverse_circles(
    circles: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    topic_counts: dict[str, int] = {}

    for circle in circles:
        topic = circle["topic"] or f"circle-{circle['id']}"
        if topic_counts.get(topic, 0) >= MAX_PER_TOPIC_FIRST_PASS:
            deferred.append(circle)
            continue

        selected.append(circle)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if len(selected) == limit:
            return selected

    return (selected + deferred)[:limit]


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
    """Rank leader Circles first, then eligible interest and trending matches."""
    current_time = now or datetime.now(timezone.utc)
    interests = set(user["topic_interests"])
    user_id = user["id"]
    activity_by_circle = _recent_activity_metrics(circles, activity_records)
    circles_by_id = {circle["id"]: circle for circle in circles}

    leader_circles = [
        circles_by_id[circle_id]
        for circle_id in leader_circle_ids
        if circle_id in circles_by_id
    ]
    leader_circles.sort(
        key=lambda circle: (
            _last_activity(circle),
            -circle["id"],
        ),
        reverse=True,
    )
    recommendations = [
        _recommendation(circle, LEADER_REASON)
        for circle in leader_circles[:limit]
    ]
    remaining_limit = limit - len(recommendations)
    if remaining_limit == 0:
        return recommendations

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
            activity_by_circle[circle["id"]].recent_reactions
            + activity_by_circle[circle["id"]].recent_comments,
            _last_activity(circle),
            -circle["id"],
        ),
        reverse=True,
    )

    high_engagement_ids = _high_engagement_circle_ids(
        eligible,
        activity_by_circle,
    )
    selected = _select_diverse_circles(eligible, remaining_limit)
    recommendations.extend(
        _recommendation(
            circle,
            _reason(
                circle,
                interests,
                topic_labels,
                activity_by_circle[circle["id"]],
                circle["id"] in high_engagement_ids,
            ),
        )
        for circle in selected
    )
    return recommendations
