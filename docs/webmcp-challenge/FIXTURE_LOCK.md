# Locked Challenge Fixture

This file is the human-readable lock for the disposable public Challenge Town. Contract tests remain the executable authority.

```text
scenario_id: harbor-wage-crisis-v1
fixture_version: 1
forecast_seeds: [101, 102, 103, 104, 105]
actual_seed: 211
initial_hash: sha256:d095c7b5c759a58e6d07f5b6a6c4c2687016ce2b64295cfaad2490010ca5cb10
expected_actual: high_food_risk_residents=1 social_tension=54 strike_risk_pct=38 stabilized_residents=5
expected_no_action: high_food_risk_residents=3 social_tension=81 strike_risk_pct=100 stabilized_residents=0 strike_event_triggered=true
```

## Initial public state

| Field | Locked value |
|---|---:|
| World version | v7 |
| World time | 2042-06-12T08:00:00Z |
| Budget | 300 SC |
| Unpaid residents | 6 |
| High-food-risk residents | 2 |
| Social tension | 68 |
| Strike risk | 74% |
| Stabilized residents | 0 |

## Intervention and 72-hour result

- The only accepted intervention costs 240 SC, leaving 60 SC, and advances v7 to v8.
- The forecast uses five fixed seeds over 72 hours. Its final ranges are: high food risk 0–1, social tension 50–58, strike risk 28–42%, and stabilized residents 5–6.
- Verification uses `actual_seed: 211`, advances v8 to v9, and records 13 points at six-hour intervals including both endpoints.
- The paired No-action control starts from the same initial snapshot and seed schedule. It ends with a strike event, so the comparison is not a separate hand-authored story.
- Reset creates a new anonymous generation at v7 and restores the exact `initial_hash` above.

## Executable lock

- Fixture constants: `backend/app/challenge/fixture.py`
- Deterministic engine constants: `backend/app/challenge/engine.py`
- Public hash and contract assertions: `backend/tests/challenge/test_contract.py`
- Prediction/actual/control assertions: `backend/tests/challenge/test_engine.py`

Any intentional fixture change must update implementation, executable tests, this file, the benchmark expectation, and the recorded E2E evidence together. A documentation-only drift is a release failure.
