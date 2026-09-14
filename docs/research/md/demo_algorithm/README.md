# Demo algorithm — testing and deployment

Use branch `feature/demo-algorithm-live-pilot`. These steps exercise the stable selector locally; they do not deploy it.

## Start the server

Stop any existing stack, then run from `src/server/`:

```sh
DEBUG=True \
COSOUND_CORE_PREDICTOR=core.predict.stable_preference_predictor \
COSOUND_MIN_LAYERS=2 \
COSOUND_MAX_LAYERS=3 \
COSOUND_MINIMUM_HOLD_SECONDS=0 \
COSOUND_MAX_STAY_SECONDS=60 \
uv run src/main.py proc runserver --procfile procfile.dev
```

Use `COSOUND_MAX_STAY_SECONDS=` for an indefinite maximum. `COSOUND_MIN_LAYERS=2` and `COSOUND_MAX_LAYERS=3` keep normal demo mixes between two and three sounds; the backward-compatible defaults are one and three. If a player has fewer assigned sounds than the minimum, the selector uses the available library rather than silencing playback. For normal demo behavior, use a 120-second minimum hold and a 300–600-second maximum stay. A finite maximum must not be shorter than the minimum hold. Restart the scheduler and worker after changing settings.

## Submit a vote

1. Open `http://localhost:8000/admin/core/player/` and select the player.
2. Under **Player Utilities → NFC URLs**, copy an upvote or downvote URL.
3. Open the URL, sign in or use anonymous login, and press the vote button.
4. Votes are throttled to one per listener per 60 seconds. The scheduler runs every 30 seconds.

`choice=1` is an upvote and `choice=0` is a downvote. A vote applies to the complete current mix, not each component sound.

## Expected behavior

- The worker task path is `core.predict.stable_preference_predictor`.
- One, two, and three layers use gains near `1.0`, `0.707107`, and `0.577350`; with the documented two-layer minimum, only the latter two should appear.
- Before the minimum hold expires, the mix stays put.
- At a finite maximum stay, at least one sound ID changes. Each decision may add one, remove one, or replace one layer; tied choices prefer a one-for-one replacement.
- With an indefinite maximum and no new evidence, a valid mix may remain forever.
- `New Prediction` prints only when the selected mix changes.

## Inspect the latest decision

Run from `src/server/`:

```sh
uv run src/main.py shell -c '
from core.models import AlgorithmDecision
d = AlgorithmDecision.objects.order_by("-decided_at").first()
print("No decision yet" if d is None else {
    "outcome": d.outcome,
    "previous": d.previous_layers,
    "selected": d.selected_layers,
    "listeners": d.active_listener_ids,
    "explanation": d.trace.get("explanation"),
})
'
```

Useful outcomes are `selected`, `retained_best`, `minimum_hold`, `maximum_stay`, `maximum_stay_unavailable`, and `retained_no_active_listeners`.

## Automated checks

```sh
uv run src/main.py test \
  core.tests.PredictorTests \
  core.tests.StableSelectionTests \
  core.tests.StablePredictorIntegrationTests \
  app.tests.PlayerExposureApiTests \
  vote.tests.SubmitVoteTests
```

From `src/player/src/`:

```sh
../.venv/bin/python -m unittest discover -s ../tests -v
```

## Production configuration

The values are environment configuration, not secrets committed to Git. Production reads them from the server's `env/.env`, which is ignored by Git and written with mode `600` by `bin/setup_env.sh`. On a fresh server, `make docker-env` now prompts for every selector setting. On an existing server, add or edit these lines directly:

```dotenv
COSOUND_CORE_PREDICTOR=core.predict.stable_preference_predictor
COSOUND_MIN_LAYERS=2
COSOUND_MAX_LAYERS=3
COSOUND_ACTIVE_LISTENER_MINUTES=5
COSOUND_MINIMUM_HOLD_SECONDS=120
COSOUND_MAX_STAY_SECONDS=300
COSOUND_DISAGREEMENT_PENALTY=0.25
COSOUND_EXPLORATION_PROBABILITY=0
COSOUND_EXPLORATION_SIZE=5
COSOUND_HOUSE_SOUND_ID=5
```

Those are recommended pilot values, not checked-in production values. `COSOUND_MAX_STAY_SECONDS=` makes forced change indefinite. `COSOUND_EXPLORATION_PROBABILITY=0` keeps the first rollout deterministic. Confirm that `COSOUND_HOUSE_SOUND_ID` exists in the production sound library, or leave it blank to disable that preferred fallback.

Deploy with `make docker-deploy`. Its release container applies the database migrations before the web, worker, and scheduler services start. If only `env/.env` changes, use `make docker-up` so Compose recreates services with the new environment; a plain container restart does not reload changed environment variables.

After deployment, confirm the worker logs show `path=core.predict.stable_preference_predictor`, submit an upvote and a downvote, and inspect the latest decision with the command above. A misspelled predictor import now stops the scheduler with a clear error instead of silently reverting to random selection.

## Restore defaults

Unset `COSOUND_MAX_STAY_SECONDS` for an indefinite stay. Remove the layer settings to restore the compatible one-to-three range. Set `COSOUND_CORE_PREDICTOR=core.predict.random_predictor` and run `make docker-up` to roll selection back; recorded decisions, exposures, and votes remain available.
