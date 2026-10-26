# Circle Recommendations API — Technical Design

## Goal

Return a ranked list of Circles for a member, with a short explanation for each
recommendation. The first version uses the supplied synthetic JSON dataset and
the Circle-level activity aggregates. It does not use post-level activity,
free-form Circle tags, embeddings, or profile-based inference.

## API

- `GET /health` returns `{"status": "ok"}`.
- `GET /recommendations?user_id=<int>&limit=<int>` returns recommendations.
- `limit` defaults to 5 and must be between 1 and 10.
- An unknown `user_id` returns HTTP 404.
- Invalid/missing query parameters use FastAPI's standard HTTP 422 response.

Successful response:

```json
{
  "user_id": 7,
  "recommendations": [
    {
      "circle_id": 5,
      "name": "Women Who Lead",
      "reason": "Matches your interest in leadership skills and has recent activity."
    }
  ]
}
```

## Data and schema

The running API loads `users.json`, `circles.json`, `memberships.json`, and
`topics.json` into memory on process startup. This keeps the initial API simple
for the small, static assignment dataset. The relational SQLite schema is
documented separately in [schema.sql](./schema.sql); it is a design deliverable,
not yet the API's persistence layer.

The schema normalizes topic interests into `user_topic_interests`, references
the canonical topic lookup from each Circle's optional primary topic, and uses
`memberships` as the user-to-Circle join table. Free-form tags and individual
activity rows are intentionally omitted from this first schema revision.
Activity aggregates remain columns on `circles`.

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

Eligible Circles are sorted by:

1. Primary topic match with the member's stated interests.
2. Most recent activity timestamp.
3. Descending feed post count in the last 30 days.
4. Descending chat message count in the last 30 days.
5. Circle ID for deterministic tie-breaking.

The first selection pass returns no more than two Circles per primary topic.
If that leaves space and eligible Circles remain, a second pass fills the
requested limit, allowing additional Circles from an already represented topic.
Circles without a primary topic are treated as separate topics for diversity.

Reasons use only the selected Circle's primary topic match, public access,
recent activity, and join policy. With no topic match (including cold start),
the reason stays general and does not claim a personal preference.

## Validation scenarios

- User 7: recommend Circles matching leadership skills and public speaking.
- User 15: avoid filling the initial list with near-duplicate negotiation Circles.
- User 23: exclude the full Promotion Path and stale Career Climbers; keep
  Level Up Collective eligible.
- User 42: return useful active/public recommendations without claiming an
  interest match.
- Also verify unknown users, limit bounds, existing memberships, and response
  fields.

## Known first-version limitations

The JSON files are loaded once per API process, so changes require a restart.
Activity freshness is a deliberately simple rule using the supplied aggregates.
The ranker does not infer member interests from job, company, location, bio, or
profile completeness. A later version can import the JSON into the documented
SQLite schema and incorporate post engagement after validating that signal.
