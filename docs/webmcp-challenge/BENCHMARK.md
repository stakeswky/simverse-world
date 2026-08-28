# Challenge paired benchmark

`ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0`

## Evidence identity

- Source HEAD: `158401eef52e412ec7cde2f65c5ffd22547d934b`
- Chromium: `151.0.7922.34`
- Browser execution recorded at: `2026-08-27T15:59:02.147Z`
- Renderer generated at: `2026-08-27T15:59:27Z`
- Raw SHA-256: `84e0f407bd12ba6c5870314abc28ba28bc2187e088bf0e84afd539399e61f97d`

## Medians

| Mode | Runs | Duration ms | Human clicks | Core tool calls |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 5 | 406.8 | 6 | 0 |
| webmcp | 5 | 278 | 2 | 4 |

## All raw rows

No run was discarded. Rows remain in paired execution order.

### ordinary-1

```json
{
  "clicks": 6,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-EDE11444",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 408.59999999403954,
  "events": [
    {
      "elapsed_ms": 0.30000001192092896,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 4.199999988079071,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 108.59999999403954,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 146.59999999403954,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 152.90000000596046,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 215.80000001192093,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 316,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 348.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 357.09999999403954,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 399.80000001192093,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 408.59999999403954,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 408.59999999403954,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "ordinary",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "ordinary-1",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-EDE11444",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### webmcp-1

```json
{
  "clicks": 2,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-AC39ECC0",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 278,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.899999976158142,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 15.699999988079071,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 51.89999997615814,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 62.89999997615814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 108,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 225.89999997615814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 241.69999998807907,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 248.2999999821186,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 270.09999999403954,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 278,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 278,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "webmcp",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "webmcp-1",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-AC39ECC0",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### ordinary-2

```json
{
  "clicks": 6,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-01D3061A",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 406.80000001192093,
  "events": [
    {
      "elapsed_ms": 0.20000001788139343,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3.5,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 115.40000000596046,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 156,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 166.10000002384186,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 214.5,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 313.2000000178814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 336.60000002384186,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 347.90000000596046,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 397.80000001192093,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 406.7000000178814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 406.80000001192093,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "ordinary",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "ordinary-2",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-01D3061A",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### webmcp-2

```json
{
  "clicks": 2,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-F88FDA81",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 285.40000000596046,
  "events": [
    {
      "elapsed_ms": 0.20000001788139343,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 11.900000005960464,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 36.5,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 45,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 79.7000000178814,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 228.90000000596046,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 243.60000002384186,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 253.2000000178814,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 275.2000000178814,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 285.30000001192093,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 285.40000000596046,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "webmcp",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "webmcp-2",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-F88FDA81",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### ordinary-3

```json
{
  "clicks": 6,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-2B93C69F",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 402.5,
  "events": [
    {
      "elapsed_ms": 0.20000001788139343,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.5,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 118.59999999403954,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 150.5,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 165.30000001192093,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 209.7000000178814,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 297.7000000178814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 333.09999999403954,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 338.30000001192093,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 393.5,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 402.40000000596046,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 402.5,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "ordinary",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "ordinary-3",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-2B93C69F",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### webmcp-3

```json
{
  "clicks": 2,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-73B0614A",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 267.30000001192093,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.300000011920929,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 15.300000011920929,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 37.69999998807907,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 46.900000005960464,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 87.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 217,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 231.40000000596046,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 238.59999999403954,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 257,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 267.19999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 267.30000001192093,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "webmcp",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "webmcp-3",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-73B0614A",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### ordinary-4

```json
{
  "clicks": 6,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-EC61F949",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 475.2000000178814,
  "events": [
    {
      "elapsed_ms": 0.10000002384185791,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.5,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 145.2000000178814,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 177,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 191.2000000178814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 238.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 343.2000000178814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 376.90000000596046,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 391.5,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 461.2000000178814,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 475.10000002384186,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 475.2000000178814,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "ordinary",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "ordinary-4",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-EC61F949",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### webmcp-4

```json
{
  "clicks": 2,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-F83B42C0",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 287.2999999821186,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 14.299999982118607,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 37.69999998807907,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 54.900000005960464,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 97.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 222.2999999821186,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 238.09999999403954,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 245.69999998807907,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 273.90000000596046,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 287.2999999821186,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 287.2999999821186,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "webmcp",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "webmcp-4",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-F83B42C0",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### ordinary-5

```json
{
  "clicks": 6,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-67A0C2A4",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 404.5,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.699999988079071,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 105.39999997615814,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 147.59999999403954,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 162,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 217,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 312.59999999403954,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 344.09999999403954,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 355.59999999403954,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 396.2999999821186,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 404.39999997615814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 404.5,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "ordinary",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "ordinary-5",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-67A0C2A4",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

### webmcp-5

```json
{
  "clicks": 2,
  "commit_evidence": {
    "budget_after_sc": 60,
    "budget_before_sc": 300,
    "budget_delta_sc": -240,
    "receipt_id": "SV-2042-CC5E5BC3",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 266.5,
  "events": [
    {
      "elapsed_ms": 0.30000001192092896,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.4000000059604645,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 17.099999994039536,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 40.80000001192093,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 53.099999994039536,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 93.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 210.40000000596046,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 226.30000001192093,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 234.80000001192093,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 256.09999999403954,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 266.40000000596046,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 266.5,
      "event": "task_completed",
      "fields": {
        "success": true
      }
    }
  ],
  "mode": "webmcp",
  "panel_switches": 2,
  "preview_rebuild_count": 0,
  "route_switches": 1,
  "run_id": "webmcp-5",
  "success": true,
  "unauthorized_attempts": 1,
  "unauthorized_probe": {
    "code": "APPROVAL_REQUIRED",
    "status": 403,
    "success": false
  },
  "unauthorized_successes": 0,
  "verify_evidence": {
    "receipt_id": "SV-2042-CC5E5BC3",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

## Slowest row

- Run: `ordinary-4`
- Mode: `ordinary`
- Duration: `475.2 ms`
- Human clicks: `6`
- Core tool calls: `0`
