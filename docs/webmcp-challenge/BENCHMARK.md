# Challenge paired benchmark

`ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0`

## Evidence identity

- Source HEAD: `11cb7e6009bd21d4eef5c7ce9c4ee918c0dfc0ff`
- Chromium: `151.0.7922.34`
- Browser execution recorded at: `2026-08-27T08:13:34.661Z`
- Renderer generated at: `2026-08-27T08:13:52Z`
- Raw SHA-256: `edd17e10902d00be0d312062b91b9d6a62b9be27a9fcfe371f1d42c9be490a83`

## Medians

| Mode | Runs | Duration ms | Human clicks | Core tool calls |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 5 | 423.6 | 6 | 0 |
| webmcp | 5 | 242.8 | 2 | 4 |

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
    "receipt_id": "SV-2042-92CEDEDC",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 379.59999999403954,
  "events": [
    {
      "elapsed_ms": 0.09999999403953552,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.0999999940395355,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 51,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 97.59999999403954,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 112.69999998807907,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 157.19999998807907,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 246.7999999821186,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 300.19999998807907,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 313.19999998807907,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 364.2999999821186,
      "event": "verification_started",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 379.5,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 379.59999999403954,
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
    "receipt_id": "SV-2042-92CEDEDC",
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
    "receipt_id": "SV-2042-5B3D9EB1",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 259.89999997615814,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.199999988079071,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 13.099999994039536,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 43.69999998807907,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 52.79999998211861,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 84.2999999821186,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 179.5,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 219.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 227.5,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 251.89999997615814,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 259.89999997615814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 259.89999997615814,
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
    "receipt_id": "SV-2042-5B3D9EB1",
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
    "receipt_id": "SV-2042-6068696C",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 388.7999999821186,
  "events": [
    {
      "elapsed_ms": 0,
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
      "elapsed_ms": 60.89999997615814,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 108.09999999403954,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 122.89999997615814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 168.2999999821186,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 255.19999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 306.5,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 322,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 374.09999999403954,
      "event": "verification_started",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 388.69999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 388.7999999821186,
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
    "receipt_id": "SV-2042-6068696C",
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
    "receipt_id": "SV-2042-BFF2E4DC",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 240.2999999821186,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
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
      "elapsed_ms": 11.099999994039536,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 33.400000005960464,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 44.29999998211861,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 79.40000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 172.90000000596046,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 208.09999999403954,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 214.2999999821186,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 232.90000000596046,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 240.19999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 240.2999999821186,
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
    "receipt_id": "SV-2042-BFF2E4DC",
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
    "receipt_id": "SV-2042-75FFC166",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 437.2999999821186,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.5,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 53.900000005960464,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 151.59999999403954,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 168.2999999821186,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 211.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 299.7999999821186,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 351,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 366.40000000596046,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 420.09999999403954,
      "event": "verification_started",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 437.19999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 437.2999999821186,
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
    "receipt_id": "SV-2042-75FFC166",
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
    "receipt_id": "SV-2042-8E6BC65C",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 234.19999998807907,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.0999999940395355,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 9.900000005960464,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 30.599999994039536,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 38.30000001192093,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 67.59999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 163.80000001192093,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 198.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 206,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 225.80000001192093,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 234.19999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 234.19999998807907,
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
    "receipt_id": "SV-2042-8E6BC65C",
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
    "receipt_id": "SV-2042-9D2A6EC6",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 431.09999999403954,
  "events": [
    {
      "elapsed_ms": 0,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.5999999940395355,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 52.70000001788139,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 150.2000000178814,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 164.30000001192093,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 210.59999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 299.5,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 349.40000000596046,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 365,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 416,
      "event": "verification_started",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 431,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 431.09999999403954,
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
    "receipt_id": "SV-2042-9D2A6EC6",
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
    "receipt_id": "SV-2042-48FC7D3C",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 254.5,
  "events": [
    {
      "elapsed_ms": 0.29999998211860657,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3.0999999940395355,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 16.69999998807907,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 42.5,
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
      "elapsed_ms": 87.09999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 185.19999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 220.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 227,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 246.59999999403954,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 254.5,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 254.5,
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
    "receipt_id": "SV-2042-48FC7D3C",
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
    "receipt_id": "SV-2042-EBA5F2C9",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 423.59999999403954,
  "events": [
    {
      "elapsed_ms": 0.09999999403953552,
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
      "elapsed_ms": 60.79999998211861,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 156.69999998807907,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 171.7999999821186,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 210.19999998807907,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 290.39999997615814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 341.39999997615814,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 356.19999998807907,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 408.39999997615814,
      "event": "verification_started",
      "fields": {
        "clicks": 1,
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 423.5,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 423.59999999403954,
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
    "receipt_id": "SV-2042-EBA5F2C9",
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
    "receipt_id": "SV-2042-9AA371E3",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 242.80000001192093,
  "events": [
    {
      "elapsed_ms": 0.10000002384185791,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.2000000178813934,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 10.900000005960464,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 33.400000005960464,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 41.60000002384186,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 76.60000002384186,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 178.2000000178814,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 212.10000002384186,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 218.7000000178814,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 236,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 242.7000000178814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 242.80000001192093,
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
    "receipt_id": "SV-2042-9AA371E3",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

## Slowest row

- Run: `ordinary-3`
- Mode: `ordinary`
- Duration: `437.3 ms`
- Human clicks: `6`
- Core tool calls: `0`
