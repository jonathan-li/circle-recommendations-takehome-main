# Circle Recommendations API — Technical Design

## Goal

Return a ranked list of Circles for a member, with a short explanation for each
recommendation. The first version uses the supplied synthetic JSON dataset and
the Circle-level activity aggregates. It uses Circle tags as a secondary topic
match, calculates a recent active-member ratio from post authors, and uses
recent reactions and comments to rank Circles within a relevance tier. It does
not use embeddings or profile-based inference.

## API

- `GET /health` returns `{"status": "ok"}`.
- `GET /recommendations?user_id=<int>&limit=<int>` returns recommendations.
- `limit` defaults to 5 and must be between 1 and 10.
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
      "active_member_ratio": 0.375,
      "reason": "Matches your interest in leadership skills and has recent activity. 38% of members posted in the last 30 days. Recent posts received 12 reactions and 4 comments."
    }
  ]
}
```

## Data and schema

The running API loads `users.json`, `circles.json`, `memberships.json`,
`topics.json`, and `activity.json` into memory on process startup. This keeps
the initial API simple for the small, static assignment dataset. The relational
SQLite schema is documented separately in [schema.sql](./schema.sql); it is a
design deliverable, not yet the API's persistence layer.

The schema normalizes topic interests into `user_topic_interests`, references
the canonical topic lookup from each Circle's optional primary topic, and uses
`memberships` as the user-to-Circle join table. Circle tags are stored
separately in `circle_tags`, preserving their source values. Individual
activity rows are represented in `activity`, referencing their Circle and
author. Activity aggregates remain columns on `circles`.

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

After any leader recommendations, eligible Circles with a primary-topic or
tag match are listed before Circles without an interest match. Within each
relevance group, eligible Circles are sorted by:

1. For interest matches, primary topic matches before tag-only matches, then
   number of matching tags.
2. Total recent post reactions and comments in the latest 30-day snapshot
   window.
3. Most recent activity timestamp.
4. Descending feed post count in the last 30 days.
5. Descending chat message count in the last 30 days.
6. Circle ID for deterministic tie-breaking.

Leader Circles are a separate high-priority group. A user's leader memberships
are returned first, ordered by Circle activity, even though those Circles are
already joined. The regular eligibility filters do not apply to this group:
capacity and public discoverability do not prevent an existing leader from
being surfaced. Leader Circles count toward the requested result limit.

A primary topic match always outranks a tag-only match. Tag overlap is a
weaker relevance signal than the Circle's declared primary topic.

Topic and tag matches remain ahead of unrelated Circles. The final section of
the list contains the highest-activity eligible Circles without a topic/tag
match, labeled “Trending HOT.” Within each relevance group, higher recent
reaction/comment volume ranks first. Explanations include the aggregate counts
used for this activity comparison.

The active-member ratio is calculated for display, not ranking: count distinct
post authors per Circle in the dataset's latest 30-day window, then divide by
the Circle's `member_count`. The API returns a 0–1 ratio and includes the
rounded percentage in the member-facing reason. If a Circle has zero members,
its ratio is 0. The activity data identifies post authors but does not identify
the members who reacted or commented, so they are not counted as distinct
active members. The 30-day window ends at the latest timestamp among Circle
activity summaries and feed posts in the snapshot. This ratio measures posting
breadth; it is a heuristic, not proof that a Circle will be more conducive to
newer members.

The first selection pass returns no more than two Circles per primary topic.
If that leaves space and eligible Circles remain, a second pass fills the
requested limit, allowing additional Circles from an already represented topic.
Circles without a primary topic are treated as separate topics for diversity.

Reasons say whether the member's interest matches the primary topic, matches a
Circle tag, or neither, and mention the Circle's recent activity. With no
primary-topic or tag match (including cold start), the reason stays general
and does not claim a personal preference. Reasons also state the percentage of
members who posted during the snapshot's latest 30-day window, plus recent
reaction/comment totals when those totals are nonzero.
Leader recommendations instead use: “You are a designated leader of this
Circle — jump in to check recent member discussions.”

## Validation scenarios

- User 7: recommend Circles matching leadership skills and public speaking.
- Rank a primary-topic match ahead of a tag-only match, and a tag-only match
  ahead of a Circle with no interest match.
- Within the same interest/tag relevance tier, prefer higher recent
  reaction/comment volume and include those counts in the explanation.
- Place high-activity Circles with no interest match after interest matches
  and label those recommendations “Trending HOT.”
- Count distinct post authors in the snapshot's latest 30-day window for the
  active-member ratio, without changing recommendation ordering.
- User 15: avoid filling the initial list with near-duplicate negotiation Circles.
- User 23: exclude the full Promotion Path and stale Career Climbers; keep
  Level Up Collective eligible.
- User 42: return useful active/public recommendations without claiming an
  interest match.
- Return the user's leader Circles first, even though the user is already a
  member, with the designated-leader explanation.
- Also verify unknown users, limit bounds, existing memberships, and response
  fields.

## Known first-version limitations

The JSON files are loaded once per API process, so changes require a restart.
Activity freshness is a deliberately simple rule using the supplied aggregates.
The ranker does not infer member interests from job, company, location, bio, or
profile completeness. A later version can import the JSON into the documented
SQLite schema and incorporate post engagement after validating that signal.
