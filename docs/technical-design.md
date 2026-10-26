# Circle Recommendations API — Technical Design

## Goal

Return a ranked list of Circles for a member, with a short explanation for each
recommendation. The first version uses the supplied synthetic JSON dataset and
the Circle-level activity aggregates. It uses Circle tags as a secondary topic
match, calculates a recent active-member ratio from post authors, and uses
recent activity to rank Circles within a relevance tier.

## API

- `GET /health` returns `{"status": "ok"}`.
- `GET /recommendations?user_id=<int>&limit=<int>` returns recommendations.
- `limit` defaults to 5 and must be between 1 and 20.
- An unknown `user_id` returns HTTP 404.
- Invalid/missing query parameters use FastAPI's standard HTTP 422 response.
- Circles where the requested user has `role=leader` are returned before
  ordinary recommendations with a leader-specific explanation.

Successful response:

```json
{
  "user_id": 7,
  "recommendations": [
    {
      "circle_id": 5,
      "name": "Women Who Lead",
      "reason": "Matches your interest in leadership skills and has recent activity. High recent engagement."
    }
  ]
}
```

## Data and schema

![Architecture diagram](./images/architecture.png)

The running API loads `users.json`, `circles.json`, `memberships.json`,
`topics.json`, and `activity.json` into memory on process startup. This keeps
the initial API simple for the small, static assignment dataset. The relational
SQLite schema is documented separately in [schema.sql](./schema.sql) as a
database design for this project; the running API does not currently use it.

The schema normalizes topic interests into `user_topic_interests`, references
the canonical topic lookup from each Circle's optional primary topic, and uses
`memberships` as the user-to-Circle join table. Circle tags are stored
separately in `circle_tags`, and individual activity rows are represented in
`activity`, referencing their Circle and author. Activity aggregates remain
columns on `circles`.

## Index rationale

Primary keys and unique constraints support ID lookups and prevent duplicate
memberships, interests, and tags. The additional indexes support likely
recommendation queries: `circles(topic_id)` narrows primary-topic matches;
`memberships(circle_id)` finds a Circle's members; and
`activity(circle_id, created_at)` retrieves a Circle's recent activity in
time order. `user_topic_interests(topic_id)` supports reverse lookups from a
topic to interested users; its primary key already supports loading one user's
interests. 

## Eligibility

Exclude a Circle when any of the following holds:

1. The member already belongs to it.
2. Its access is not `public`.
3. It is full (`max_members` is not null and `member_count >= max_members`).
4. Its latest activity is more than 90 days old, it has zero feed posts in the
   last 30 days, and it has at most five chat messages in that period.

Request-to-join Circles remain eligible. Their explanation says that a join
request is required.

## Ranking and explanation

First, Circles that users lead are recommended with high priority so they can
easily check in on activity. Leader Circles contribute to the limit.
After any leader recommendations, eligible Circles with a primary-topic or
tag match are listed before Circles without an interest match. Within each
relevance group, eligible Circles are sorted by:

1. For interest matches, primary topic matches before tag-only matches, then
   number of matching tags.
2. Total recent post reactions and comments in the latest 30-day snapshot
   window.
3. Most recent activity timestamp.
4. Circle ID for deterministic tie-breaking.

The first selection pass returns no more than two Circles per primary topic.
If that leaves space and eligible Circles remain, a second pass fills the
requested limit, allowing additional Circles from an already represented topic.
Circles without a primary topic are treated as separate topics for diversity.

Reasons say whether the member's interest matches the primary topic, matches a
Circle tag, or neither, and mention the Circle's recent activity. With no
primary-topic or tag match (including cold start), the reason stays general
and does not claim a personal preference.

Reasons show “High member activity” when the active-member ratio is at least 0.4.
If a Circle has zero members, its ratio is 0. Higher ratios should be conducive to
newer members.
The activity data identifies post authors but does not identify the members
who reacted or commented, so they are not counted as distinct active members.

Eligible Circles in the top quartile for combined recent reactions and
comments receive the “High recent engagement” reason label.

## Production scale

This version loads the full JSON dataset into memory, which is simple but does
not scale as data grows or changes. At larger scale, I would move the data to
PostgreSQL and fetch only the candidate Circles needed for each request. I
would also update activity aggregates outside the request path. If database
reads later become a bottleneck, I would add Redis to cache frequently
requested recommendations. Table updates would use separate transactional
write operations, keeping recommendation calls focused on reading consistent
data. Writes would invalidate affected cached recommendations if caching is
added.

## Notes

With more time some features to consider:

1. Evaluate recommendation outcomes and consider ML model with more data to train on
2. Ability to parse the users.bio for improved understanding of user needs (can parse topics or slugs)
3. Create a supplementary relationship table between topics and use to improve heuristics
