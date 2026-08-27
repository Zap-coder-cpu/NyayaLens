# Retrieval evaluation labels

These files are small regression sets, not exhaustive relevance judgments. A
case absent from a query is **unjudged** and must not be interpreted as legally
irrelevant.

Each query has the following fields:

- `id`: stable query identifier;
- `query`: the natural-language facts or legal issue;
- `relevance`: reviewer-supplied case IDs with integer grades (`3` strongly
  relevant, `1` relevant, and `0` explicitly not relevant);
- `non_relevant` (optional): additional reviewer-confirmed negatives; and
- `contradictory` (optional): reviewer-confirmed results that contradict a
  material fact or legal constraint in this particular query and should not be
  returned as a match.

Do not add `non_relevant` or `contradictory` entries merely because a case was
not returned, looks unfamiliar, or was flagged by the same ranking heuristic
being evaluated. Labels should come from review of the source judgment. An
empty `contradictory` array means the query was reviewed and no known
contradictory judgment was labelled; an absent field means contradiction review
has not been performed.

`evaluate.py` reports judged-only precision with judged coverage, known-positive
MRR/recall, condensed nDCG, and pairwise preference accuracy derived from
unequal relevance grades. Contradiction metrics remain `null` until the active
set contains explicit contradiction review. Read every metric together with
the emitted label summary and limitations.
