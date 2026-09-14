# CoSound demo algorithm and live pilot — focused implementation handoff

Prepared 2026-09-11 from the sibling `ALGORITHM_EXPERIMENTS_HANDOFF.md` and the demo-first product direction agreed afterward. This document is the primary scope guide for a new implementation subagent. Consult the larger handoff for audited repository facts and edge-case rationale, but do not expand this assignment into its full E0–E6 research program.

## 0. Implementation status — 2026-09-13

Implementation is present on branch `feature/demo-algorithm-live-pilot`. Do not restart it from scratch.

- Local startup, voting, timed-change, inspection, and rollback steps are in `README.md` in this directory.
- The pure selector is under `src/server/src/core/prediction/`.
- The stable task entry point is in `src/server/src/core/predict.py`; its Django adapter and persistence logic are isolated in `src/server/src/core/prediction/live.py`. The random task remains the default and rollback path.
- Additive decision/exposure models and vote attribution fields have forward migrations.
- `/player` returns additive decision/exposure IDs, and an authenticated acknowledgement endpoint is available.
- The player acknowledgement is best-effort and skipped if a requested layer is unavailable locally.
- Focused selector, random rollback, API, vote, and player-client tests pass.
- Django reports no model/migration drift and no system-check issues.
- No non-test database migration has been run, the stable predictor has not been enabled in a deployment, and no physical player or speaker playback has been started.

The broad application test command must name app labels in this repository. The latest run with `DEBUG=True` reached 137 tests and had only three unrelated existing library-template expectation failures. With production-style static handling and no collected manifest, template/admin cases additionally fail on missing static entries. The directly impacted test set is green; do not “fix” unrelated UI files as part of this handoff.

## 1. Objective

Build a small CoSound selector that is proven offline and then deployed behind a reversible configuration flag for the live demo. It must:

1. work well enough for a convincing demo;
2. can be explained to a nontechnical visitor;
3. behaves deterministically and does not change the room unnecessarily;
4. uses each live player's assigned `Sound` library and existing playback stack;
5. replace the random live choice when explicitly enabled;
6. persist decisions, playback acknowledgements, and attributed feedback that can later support supervised learning or contextual-bandit research.

This is not an ML or RL system. It is a transparent **Stable Preference Mixer** whose listener-scoring component can be replaced by a learned model later. The deliverable has two mandatory gates:

1. **Prediction gate:** deterministic pure selector and focused tests.
2. **Live pilot gate:** Django adapter, persisted decision/exposure records, player acknowledgement, vote attribution, feature flag, and rollback verification.

Use this conceptual boundary:

```text
listener evidence -> per-listener candidate scores
per-listener scores -> group score
group score + room constraints -> selected mix
selected mix -> explanation and decision trace
```

## 2. Repository facts and boundaries

Work in the `cosound` application repository. At preparation time, HEAD was `88c2c19a8976de8a9d050cf14639bc153b5036b5`, with user changes in:

- `src/server/src/core/predict.py`
- `src/server/src/core/tests.py`
- `src/server/vite/package-lock.json`

Recheck status before working. Preserve those changes and all other unrelated work.

The application already defines Django models for `Sound`, `SoundLayer`, `Cosound`, `Listener`, `Player`, and `Vote`, plus Pydantic `Prediction` and `PredictionLayer` values in `src/server/src/core/models.py`. Do not create a competing ORM or duplicate the product database schema.

The offline laboratory still needs a few lightweight, immutable values because:

- importing the application models requires Django and database configuration;
- stored `Cosound` identity rounds gains upward to 0.05, while research decisions must retain exact requested gains;
- current collection membership is not a timestamped save history;
- the product does not yet model a complete decision/exposure ledger;
- catalog availability, prepared-audio paths, and content hashes live in the portable snapshot rather than the `Sound` database row.

Prefer names that make the distinction clear, such as `CatalogSound`, `MixSpec`, `EvidenceEvent`, `RoomState`, and `DecisionTrace`. The live adapter translates Django objects into these values and a selected `MixSpec` into the existing `Prediction` type.

Keep the pure, Django-independent helpers under `src/server/src/core/prediction/` so the existing server Docker build includes exactly the code tested by `core/tests.py`. Use multiple modules only where they make the implementation clearer; do not create a general research framework or a second copy of the selector.

During the prediction gate:

- do not change the live predictor;
- do not add migrations;
- do not query or rewrite a production database;
- do not start the physical player or speaker playback;
- do not treat synthetic listener histories as real evidence of visitor preference.

After the prediction gate passes, live integration is in scope. Expected existing files touched are:

- `src/server/src/core/models.py` — additive decision/exposure persistence and the player's nullable current-exposure pointer;
- `src/server/src/core/predict.py` — thin configurable stable task entry point, preserving the random predictor;
- `src/server/src/core/tests.py` — predictor, transaction, fallback, and rollback tests;
- `src/server/src/vote/models.py` — nullable exposure attribution on votes;
- `src/server/src/vote/views.py` — attach new votes to the current exposure without rewriting historical votes;
- `src/server/src/vote/tests.py` — attributed and legacy-unattributed vote tests;
- `src/server/src/app/api.py` and `src/server/src/app/tests.py` — expose decision/exposure identity and accept player acknowledgement;
- `src/server/src/config/settings.py` — environment-controlled predictor selection with the current random predictor as default;
- `src/player/src/app/client.py` and `src/player/src/app/tui.py` — acknowledge receipt/application of a selected exposure without claiming audible confirmation.

Add forward-only Django migrations under `core/migrations/` and `vote/migrations/`. Do not edit old migration files. `src/server/src/core/predict.py` and `src/server/src/core/tests.py` already contain user changes; merge with them deliberately rather than replacing either file. All instrumentation must be invisible to the visitor flow and must fail open: acknowledgement failure cannot stop playback, and missing attribution cannot stop a vote.

## 3. Existing catalog and audio

The live selector uses `Player.library()` and the current Django `Sound` IDs/tags as its authoritative action set. It must work for any assigned library; do not hard-code the audited 17 IDs into production logic.

The sibling `ALGORITHM_CATALOG_SNAPSHOT.json` documents the current 17-sound demo library and remains useful for review fixtures. The physical player already resolves and conditions audio. Prediction code must not read, rewrite, validate, download, or play cached audio. A separate offline preview belongs to the larger experiment handoff and is not required for this focused live pilot.

## 4. Stable Preference Mixer

### 4.1 Candidate mixtures

For a library of `n` available recordings, enumerate every subset inside the configured inclusive layer-count range. The backward-compatible defaults are one to three distinct sound IDs; the recommended live demo configuration is two to three. Sort sound IDs within a mix and sort candidates canonically.

For a `k`-layer mix, give every layer the fixed gain:

```text
gain = 1 / sqrt(k)
```

With the default one-to-three range, the 17-sound catalog must produce:

- 17 single-layer candidates;
- 136 two-layer candidates;
- 680 three-layer candidates;
- 833 candidates total.

This is small enough for exhaustive scoring. Do not introduce an optimizer, continuous gain search, learned embedding, or compatibility model in this deliverable.

Use a canonical mix key built from sorted sound IDs and gains serialized to six decimal places with decimal round-half-even. Preserve the original requested floating-point gains separately. Never use Python's `hash()`, the application's gain-agnostic `Cosound.hashset`, or the rounded database identity as the exact decision key.

### 4.2 Evidence accepted by the live demo

The implemented live adapter reads only existing application data available at decision time:

- listeners with a vote at this player during the configured recent-activity window;
- each active listener's current saved-sound collection as a clearly labelled present-time snapshot;
- exact whole-mixture votes linked to an exposure;
- historical rounded `Cosound` votes, mapped through the named legacy sound-set adapter.

Normalize stored vote values through the versioned adapter:

- `1` means positive;
- `0` means negative;
- legacy `-1` means negative;
- every other value is rejected from scoring and counted in the decision snapshot;
- missing feedback is unobserved, not negative.

At decision time `t`, use only rows with `created_at <= t`. The current schema has no separate observation timestamp or collection-membership event history, so do not claim stronger temporal guarantees. Event-level fixtures, deduplication, and `observed_at` handling remain part of the larger research handoff rather than this focused live implementation.

A saved sound is weak positive evidence about that recording's tags. It is not a vote, and unsaved sounds are not negative examples. A whole-mixture downvote changes only the score for that exact mix; do not label all its component recordings as disliked.

### 4.3 Per-listener scoring

For each listener, build a tag distribution from saved sounds:

1. Each saved sound contributes total mass 1, divided evenly among its normalized tags.
2. Normalize the accumulated mass across all saved sounds.
3. A candidate sound's affinity is the profile mass assigned to its tags.
4. A mix's affinity is the gain-squared weighted average of its sound affinities.

Define the weak tag prior:

```text
a_i(m) = 0.5 + 0.25 * affinity_i(m)
```

Empty history, untagged saves, or zero tag overlap returns `0.5`.

Incorporate direct votes on the exact mix:

```text
u_hat_i(m) = (positive_votes_i,m + 2 * a_i(m))
             / (total_votes_i,m + 2)
```

This is a transparent heuristic in `[0,1]`, not a calibrated prediction of human satisfaction. Every listener uses the same function. Account type and amount of history must not change the person's social weight.

### 4.4 Group scoring

For each candidate, compute:

```text
group_score(m) = mean_i(u_hat_i(m))
                 - 0.25 * population_std_i(u_hat_i(m))
```

This means: favor what listeners like on average, with a small penalty for strong disagreement. Record the mean, minimum, population standard deviation, and final group score for every candidate.

Use equal weight for every active listener. More history may improve a prediction; it never grants more control over the room.

For deterministic selection, compare scores at a documented fixed precision. Resolve final ties in this order:

1. retain the current mix if it is valid and tied;
2. prefer fewer layers;
3. prefer the first canonical mix key.

### 4.5 Active listeners and empty-room behavior

The live adapter approximates presence using listeners with a recorded vote at that player in the previous five minutes. Label that as an activity proxy, not confirmed physical presence. Richer offline presence fixtures belong to the larger research handoff.

When there are no active listeners:

1. retain the current valid mix;
2. otherwise use a configured valid house mix;
3. otherwise return an explicit empty/no-action result.

The default configuration uses sound ID 5 as the house mix when that sound belongs to the player, but it is arbitrary and configurable. Do not encode a claim that everyone likes rain.

### 4.6 Stability constraints

The room should feel intentional rather than twitchy:

- hold an unchanged valid mix for at least 120 seconds before an elective change;
- permit at most one layer edit per change;
- retain the current mix as a feasible action;
- apply constraints before selecting, by scoring only reachable candidates;
- reset `last_change_at` only when the mix actually changes.

For layer sets `old` and `new`, define one permitted edit as:

```text
max(count(new - old), count(old - new)) <= 1
```

Thus one-for-one replacement is one edit. If a current layer becomes unavailable, remove it as a forced-validity exception and record the reason.

## 5. Optional safe exploration

Exploration is off by default for the first demo. Make it an explicit configuration flag.

When enabled on an eligible decision:

1. rank the reachable candidates normally;
2. define an exploration set as the top five candidates, or fewer if fewer are reachable;
3. with probability `0.95`, select the normal winner;
4. with probability `0.05`, select uniformly from that recorded set.

If the set has size `M`, log exact action probabilities:

```text
P(winner) = 0.95 + 0.05 / M
P(other candidate in set) = 0.05 / M
P(candidate outside set) = 0
```

Use a supplied seeded RNG and record the seed/stream and whether the exploratory branch fired. During a forced hold, action probability is 1 for retention. Do not describe logged probabilities as support for actions that had probability zero.

This limited exploration can later support contextual-bandit analysis within its covered action space. It does not by itself make the system RL-ready or permit unbiased evaluation of arbitrary alternative policies.

## 6. Explanation contract

Every persisted live decision must be understandable without reading code. Save both structured facts and a concise generated explanation in its trace. It should be able to say, for example:

> Two active listeners have saved rain or nature recordings, giving this mix weak tag support. No listener has voted on this exact mix. It had the best group score among reachable choices, and changing to it requires one layer replacement.

Explanations must distinguish:

- explicit saved-sound evidence;
- direct votes on an exact mix;
- neutral cold-start assumptions;
- group mean and disagreement penalty;
- holds, reachability, ties, fallbacks, and exploration.

Do not state that the algorithm knows a listener likes a sound when it only inferred weak tag affinity.

## 7. Decision and exposure-shaped logging

Logging is designed offline and persisted during the mandatory live pilot.

Each persisted live trace contains:

- schema version and unique decision ID;
- policy, scoring, feature, candidate, and configuration versions;
- decision time and evidence cutoff;
- player ID in structured logs and active listener database IDs in the row;
- previous exact mix and last actual change time;
- a reproducible candidate-manifest reference, counts, and the top scored candidates;
- per-listener predictions for the persisted top candidates;
- candidate mean, minimum, disagreement, and final score for those candidates;
- selected exact layers/gains and canonical key;
- hold, transition, fallback, tie, and exploration reasons;
- a concise plain-English explanation;
- selected-action probability, the nonzero action-probability map, exploration flag, and seed.

The separate `input_snapshot` retains the library IDs/tags, current saved-sound profiles, and sufficient vote counts needed to reproduce scoring without copying every candidate into the database. It excludes wall-clock duration, absolute output paths, and audio data.

Define an offline `ExposureRecord` shape for later deployment with:

- exposure and decision IDs;
- selected exact mix;
- commanded time;
- optional player acknowledgement time;
- optional estimated audible start/end;
- status such as `commanded`, `player_acknowledged`, `ended`, or `failed`.

Future feedback should link to an exposure ID and retain listener, time, raw value, player/context, and attribution confidence. A server selection is not proof that the physical player rendered that exact mix audibly.

The useful learning dataset is the chain:

```text
decision -> action probability -> exposure -> attributed feedback
```

Existing votes without reliable exposure linkage remain usable with an explicit lower attribution grade.

### 7.1 Minimal live persistence

Add two application records; exact Django field names may follow repository conventions, but their semantics must remain stable and versioned:

1. **AlgorithmDecision:** one row for every scheduled selection attempt, including holds and no-action results. Store player, policy/config versions, decision time, previous and selected exact layers, active-listener input summary, canonical trace, selected-action probability, exploration flag, and reason.
2. **PlaybackExposure:** the interval during which one selected mix is believed to be presented. Store player, opening decision, exact layers, commanded time, first player acknowledgement, estimated transition completion, end time, and status. Attribution quality belongs to feedback rows such as `Vote`.

Add a nullable `Player.current_exposure` relationship. Add a nullable `Vote.exposure` relationship and an attribution-quality field so historical votes remain valid and explicitly unattributed.

Every scheduler run should:

1. lock/reload the target player inside an atomic transaction;
2. load only that player's current library, recent listener activity, current collection snapshots, and votes available at decision time;
3. map those Django values into the pure selector;
4. create an `AlgorithmDecision`, including holds;
5. when the exact mix changes, close the preceding exposure, open a new one, and update `Player.playing` plus `Player.current_exposure` consistently;
6. when the mix is retained, keep the existing exposure open and link the hold decision to it;
7. on failure, leave the preceding valid playback state intact and record/log the failure rather than partially updating state.

Use recent interaction within five minutes as the first live active-listener proxy. Current saved collections may seed weak tag profiles, but mark them `current_collection_snapshot`; do not pretend their save times are known. Map legacy rounded `Cosound` votes to the fixed-gain candidate with the same sound set only under a named legacy adapter. New votes should resolve the exact mix through their exposure record.

The API response used by the player should include backward-compatible `decision_id` and `exposure_id` fields. After the player receives and queues a changed state, it should call an authenticated acknowledgement endpoint with the exposure ID and expected transition duration. Record this as `player_acknowledged`, not `audibly_confirmed`.

On vote submission, attach `Player.current_exposure`. Mark attribution lower or uncertain when no acknowledgement exists, when the vote falls inside an estimated transition window, or when the exposure is otherwise inconsistent. Never block an ordinary vote merely because attribution is uncertain.

### 7.2 Live feature flag and rollback

Keep `core.predict.random_predictor` available. Add a separate stable predictor task and select it through `COSOUND_CORE_PREDICTOR`. The checked-in/default setting remains the current random predictor; the live demo environment explicitly enables the stable predictor.

After tests and migrations succeed in a nonproduction environment, enable with:

```text
COSOUND_CORE_PREDICTOR=core.predict.stable_preference_predictor
```

Exploration defaults to `0`; do not enable it merely to demonstrate the selector. Other supported environment controls are minimum/maximum layer counts, the active-listener window, minimum hold, optional maximum stay, disagreement penalty, exploration size/probability, and optional house-sound ID documented in `config/settings.py`. A blank maximum stay means indefinite. At a finite deadline, exclude the current sound set but retain the one-layer edit constraint; prefer a one-for-one replacement when scores tie. The no-listener house fallback also respects the configured layer minimum by including the house sound in the smallest valid mix.

Rollback must require only changing that setting and restarting the scheduler/worker. Rolling back selection must not delete decision, exposure, or attributed vote history. A predictor exception must not clear a valid current mix.

## 8. Audio boundary

The existing player remains responsible for downloading, conditioning, mixing, crossfading, and playing audio. This focused change only chooses `PredictionLayer` values and observes whether the player acknowledges receiving them.

Do not change gain conditioning, spatialization, reverb, master volume, speaker behavior, or cached audio. An offline rendered preview may be produced later under the larger experiment handoff, but it must not block this live demo selector.

## 9. Minimal project shape

Keep the split small. `domain.py` owns validated portable values; `selector.py` owns enumeration, scoring, aggregation, stability, and optional exploration; `live.py` adapts Django evidence and persists decisions. Do not split further unless a concrete responsibility becomes difficult to understand or test.

```text
src/server/src/core/
  predict.py           # small task entry points; random remains the default
  prediction/
    __init__.py
    domain.py          # portable validated values and exact mix keys
    selector.py        # candidates, scoring, holds/max stay, exploration
    live.py            # Django evidence adapter, transactions, persisted traces
  tests.py             # existing random tests plus focused stable tests
```

`domain.py` and `selector.py` must not import Django, ORM models, audio libraries, or server settings. Django integration stays in `live.py`, while `core.predict` remains the small task entrypoint. Do not add production dependencies for this work.

## 10. Focused test scenarios

The checked-in focused tests cover:

1. six- and 17-sound candidate counts, including configurable layer bounds;
2. input-order invariance and invalid duplicate/nonfinite inputs;
3. saved-tag affinity and a balanced result under conflicting profiles;
4. an exact-mix downvote without component-level negative labels;
5. minimum hold, optional maximum stay, and one-layer reachability;
6. exact exploration probabilities;
7. live selection, decision/exposure persistence, hold behavior, stale-exposure healing, and transactional failure rollback;
8. authenticated/idempotent player acknowledgement and vote attribution quality.

Broader authored-event fixtures and offline audio previews remain in `ALGORITHM_EXPERIMENTS_HANDOFF.md`; they are not prerequisites for this focused live pilot.

## 11. Tests and acceptance gate

Before the real demo cases, retain only the small mathematical correctness checks needed to trust the implementation:

- six synthetic sound IDs generate exactly 41 unique one-to-three-layer candidates;
- 17 real IDs generate exactly 833 candidates with the 17/136/680 breakdown;
- input permutations do not change candidates or deterministic decisions;
- duplicate sound/listener IDs and nonfinite gains fail clearly;
- equivalent layer order yields one exact mix key;
- a gain change above key precision changes the key;
- empty library and no-active-listener behavior are typed and explained;
- stability and one-layer reachability are enforced before scoring the winner;
- a fixed seed produces exact recorded exploration probabilities.

The prediction gate is complete when:

- the pure selector imports without Django setup;
- six toy sounds produce 41 candidates and 17 sounds produce the 17/136/680 breakdown;
- focused pure cases produce deterministic explained decisions;
- exploration-off decisions are deterministic;
- no audio, network, database, or server startup is required for pure selector tests;
- the existing random predictor behavior and tests remain intact;
- synthetic fixtures are not presented as real visitor evidence.

The live pilot gate is complete when:

- the stable predictor uses only a player's assigned library and evidence available at decision time;
- the random predictor still passes its existing tests and remains the default/rollback path;
- each scheduler attempt persists an explained decision, including holds and no-action results;
- changed mixes atomically update `Player.playing`, exposure state, and the associated decision;
- unchanged mixes do not open duplicate exposures or reset the hold timer;
- the player acknowledges the exposure it received without claiming audible confirmation;
- new votes link to the current exposure when possible, while old/unattributed votes continue to work;
- transition-window votes remain accepted and are marked uncertain;
- repeated scheduler jobs and acknowledgements are idempotent enough not to duplicate live state;
- an injected selector or persistence failure leaves the last valid mix available;
- enabling and disabling `COSOUND_CORE_PREDICTOR` demonstrates activation and rollback;
- migrations apply forward on a representative database and do not rewrite existing votes;
- server, vote, and player tests pass alongside the pure selector tests.

## 12. Work order

1. Recheck repository state and inspect existing application types; write down the adapter mapping rather than duplicating ORM models.
2. Add only `core/prediction/domain.py`, `selector.py`, and the Django adapter `live.py` needed to keep `core/predict.py` readable.
3. Implement candidate enumeration and the small correctness tests.
4. Implement evidence normalization and tag-and-vote per-listener scoring.
5. Implement mean-minus-disagreement aggregation and deterministic tie-breaking.
6. Implement room holds, one-layer reachability, and no-active-listener fallback.
7. Add optional seeded safe exploration and verify logged propensities.
8. Complete and review the prediction gate.
9. Add `AlgorithmDecision`, `PlaybackExposure`, player/current-exposure linkage, vote attribution fields, and forward migrations.
10. Adapt current Django player/library/listener/vote data into the pure selector in a new stable predictor task.
11. Persist selection, exposure changes, and `Player.playing` atomically; retain the current mix on failure and record an error decision when the database permits.
12. Extend the player API response and add authenticated, idempotent exposure acknowledgement.
13. Attach votes to the current exposure with explicit transition/attribution quality.
14. Add application and player tests, then exercise stable-predictor activation and random-predictor rollback in a nonproduction environment.
15. Run the live pilot only after migrations, rollback, privacy, and no-speaker-surprise checks are reviewed.

Do not begin large E1 simulations, E2 profile comparisons, E3 room studies, B0 dataset acquisition, ML training, or RL before the live pilot gate passes. Do not deploy directly to production as the first integration test.

## 13. Upgrade path after the demo

Keep the interfaces stable so a learned scorer can later replace the scoring portion of `selector.py` while candidate generation, aggregation, stability, explanations, and tracing remain comparable.

With sufficiently attributed data, the likely progression is:

1. measure simple held-out vote prediction against the heuristic;
2. train a supervised probability model using only evidence available at decision time;
3. compare it offline and in a prospective controlled deployment;
4. consider a contextual bandit only after logged exploration provides known action probabilities and adequate overlap;
5. consider full RL only if delayed consequences are important and simpler methods demonstrably fail.

Do not call ordinary deterministic vote logs counterfactual training data. Do not infer rewards for unplayed mixes. Keep every listener equally weighted in group aggregation even if prediction confidence differs.

## 14. Ready-to-use subagent prompt

> Read `docs/research/md/demo_algorithm/DEMO_ALGORITHM_SUBHANDOFF.md`, then consult `docs/research/md/demo_algorithm/ALGORITHM_EXPERIMENTS_HANDOFF.md` only for supporting audited details. First pass the prediction gate with small pure helpers under `src/server/src/core/prediction/` and tests in `core/tests.py`. Then complete the live pilot: add additive decision/exposure persistence and migrations, integrate a separately configurable stable predictor without removing the random predictor, add best-effort player acknowledgement, attribute new votes to exposures, and verify activation plus rollback. Preserve existing edits, UI behavior, voting behavior, and cached audio. Do not download public datasets or expand into the full E0–E6 program. Finish both acceptance gates with tests, traces, migration evidence, and the exact files changed.
