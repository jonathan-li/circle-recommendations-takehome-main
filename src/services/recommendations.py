from datetime import datetime, timedelta, timezone
from typing import Any

INACTIVE_AFTER = timedelta(days=90)
MAX_PER_TOPIC_FIRST_PASS = 2


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


def _reason(
    circle: dict[str, Any],
    interests: set[str],
    topic_labels: dict[str, str],
) -> str:
    topic = circle["topic"]
    if topic in interests:
        label = topic_labels.get(topic, topic.replace("-", " "))
        reason = f"Matches your interest in {label.lower()} and has recent activity."
    else:
        reason = "A public Circle with recent activity."

    if circle["join_policy"] == "request":
        reason += " You'll need to request to join."
    return reason


def recommend_circles(
    user: dict[str, Any],
    circles: list[dict[str, Any]],
    memberships: set[tuple[int, int]],
    topic_labels: dict[str, str],
    limit: int = 5,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return eligible Circles ranked by topic match and recent activity."""
    current_time = now or datetime.now(timezone.utc)
    interests = set(user["topic_interests"])
    user_id = user["id"]

    eligible = [
        circle
        for circle in circles
        if (user_id, circle["id"]) not in memberships
        and circle["access"] == "public"
        and not _is_full(circle)
        and not _is_inactive(circle, current_time)
    ]
    eligible.sort(
        key=lambda circle: (
            circle["topic"] in interests,
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
        if len(selected) == limit:
            break

    if len(selected) < limit:
        selected_ids = {circle["id"] for circle in selected}
        selected.extend(
            circle for circle in deferred
            if circle["id"] not in selected_ids
        )
        selected = selected[:limit]

    return [
        {
            "circle_id": circle["id"],
            "name": circle["name"],
            "reason": _reason(circle, interests, topic_labels),
        }
        for circle in selected
    ]
