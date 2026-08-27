# Challenge paired benchmark

`ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0`

## Evidence identity

- Source HEAD: `8365fb3e75acb60b89621e0f68e6f13c54ef4477`
- Chromium: `151.0.7922.34`
- Browser execution recorded at: `2026-08-27T08:46:15.992Z`
- Renderer generated at: `2026-08-27T08:46:33Z`
- Raw SHA-256: `7b2865e7307b1692ac14a350fd05966371bd8272a0e9554287e00d86f5b082eb`

## Medians

| Mode | Runs | Duration ms | Human clicks | Core tool calls |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 5 | 398.2 | 6 | 0 |
| webmcp | 5 | 237.7 | 2 | 4 |

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
    "receipt_id": "SV-2042-DB97EC7D",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 372.30000001192093,
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
      "elapsed_ms": 77.59999999403954,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 111.5,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 121.90000000596046,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 166.5,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 260.69999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 292.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 305.5,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 361.90000000596046,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 372.19999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 372.30000001192093,
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
    "receipt_id": "SV-2042-DB97EC7D",
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
    "receipt_id": "SV-2042-0A1FF434",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 258.09999999403954,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
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
      "elapsed_ms": 15.599999994039536,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 47,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 55.599999994039536,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 91.09999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 212.09999999403954,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 225.69999998807907,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 232.2999999821186,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 250.7999999821186,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 258.09999999403954,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 258.09999999403954,
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
    "receipt_id": "SV-2042-0A1FF434",
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
    "receipt_id": "SV-2042-19CE1BC0",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 354.30000001192093,
  "events": [
    {
      "elapsed_ms": 0.30000001192092896,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.800000011920929,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 66.10000002384186,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 95.30000001192093,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 102.2000000178814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 141.90000000596046,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 238,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 274.7000000178814,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 287.7000000178814,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 340,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 354.2000000178814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 354.30000001192093,
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
    "receipt_id": "SV-2042-19CE1BC0",
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
    "receipt_id": "SV-2042-0A4A1CD5",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 237.69999998807907,
  "events": [
    {
      "elapsed_ms": 0.29999998211860657,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 2.9000000059604645,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 12.900000005960464,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 36.29999998211861,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 44,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 71.59999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 195.19999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 207.19999998807907,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 213.59999999403954,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 231.40000000596046,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 237.69999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 237.69999998807907,
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
    "receipt_id": "SV-2042-0A4A1CD5",
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
    "receipt_id": "SV-2042-38F3D499",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 428.80000001192093,
  "events": [
    {
      "elapsed_ms": 0.30000001192092896,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3.699999988079071,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 109.59999999403954,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 151.69999998807907,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 162.09999999403954,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 207,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 320,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 353.69999998807907,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 363,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 418.19999998807907,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 428.69999998807907,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 428.80000001192093,
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
    "receipt_id": "SV-2042-38F3D499",
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
    "receipt_id": "SV-2042-6177590C",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 231.69999998807907,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
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
      "elapsed_ms": 12.399999976158142,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 35.89999997615814,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 43.69999998807907,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 70,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 189.19999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 199.89999997615814,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 207.2999999821186,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 225.69999998807907,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 231.59999999403954,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 231.69999998807907,
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
    "receipt_id": "SV-2042-6177590C",
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
    "receipt_id": "SV-2042-3508AAC0",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 398.2000000178814,
  "events": [
    {
      "elapsed_ms": 0.30000001192092896,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3.2000000178813934,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 95.59999999403954,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 137.90000000596046,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 148.40000000596046,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 191.09999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 285,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 319.30000001192093,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 331.5,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 385.40000000596046,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 398.2000000178814,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 398.2000000178814,
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
    "receipt_id": "SV-2042-3508AAC0",
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
    "receipt_id": "SV-2042-31555872",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 222.59999999403954,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.399999976158142,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 9.399999976158142,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 28.599999994039536,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 37.39999997615814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 65.7999999821186,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 175.69999998807907,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 188.39999997615814,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 195.19999998807907,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 215.19999998807907,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 222.59999999403954,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 222.59999999403954,
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
    "receipt_id": "SV-2042-31555872",
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
    "receipt_id": "SV-2042-440CC3FC",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 0,
  "duration_ms": 430.40000000596046,
  "events": [
    {
      "elapsed_ms": 0.19999998807907104,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 3.199999988079071,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 121.2999999821186,
      "event": "crisis_identified",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 154.19999998807907,
      "event": "preview_requested",
      "fields": {
        "clicks": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 163.7999999821186,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 219.09999999403954,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 315.7999999821186,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 350.59999999403954,
      "event": "commit_attempted",
      "fields": {
        "clicks": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 363.69999998807907,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 417.69999998807907,
      "event": "verification_started",
      "fields": {
        "clicks": 1
      }
    },
    {
      "elapsed_ms": 430.40000000596046,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 430.40000000596046,
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
    "receipt_id": "SV-2042-440CC3FC",
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
    "receipt_id": "SV-2042-B4DE55D8",
    "world_after_version": 8,
    "world_before_version": 7
  },
  "core_tool_calls": 4,
  "duration_ms": 305.10000002384186,
  "events": [
    {
      "elapsed_ms": 0.10000002384185791,
      "event": "task_started",
      "fields": {}
    },
    {
      "elapsed_ms": 1.7000000178813934,
      "event": "panel_opened",
      "fields": {
        "panel": "living_world",
        "route": "challenge"
      }
    },
    {
      "elapsed_ms": 19.700000017881393,
      "event": "crisis_identified",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 62.30000001192093,
      "event": "preview_requested",
      "fields": {
        "core_tool_calls": 1,
        "preview_rebuild_count": 0
      }
    },
    {
      "elapsed_ms": 78.7000000178814,
      "event": "preview_ready",
      "fields": {}
    },
    {
      "elapsed_ms": 131.10000002384186,
      "event": "approval_viewed",
      "fields": {
        "panel": "approval",
        "unauthorized_attempts": 1
      }
    },
    {
      "elapsed_ms": 255.60000002384186,
      "event": "approval_granted",
      "fields": {
        "clicks": 2
      }
    },
    {
      "elapsed_ms": 269.10000002384186,
      "event": "commit_attempted",
      "fields": {
        "core_tool_calls": 1,
        "unauthorized_attempts": 0
      }
    },
    {
      "elapsed_ms": 276,
      "event": "commit_succeeded",
      "fields": {
        "unauthorized_successes": 0
      }
    },
    {
      "elapsed_ms": 297.7000000178814,
      "event": "verification_started",
      "fields": {
        "core_tool_calls": 1
      }
    },
    {
      "elapsed_ms": 305.10000002384186,
      "event": "verification_ready",
      "fields": {
        "success": true
      }
    },
    {
      "elapsed_ms": 305.10000002384186,
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
    "receipt_id": "SV-2042-B4DE55D8",
    "tick_count": 12,
    "world_after_version": 9,
    "world_before_version": 8
  },
  "wrong_selections": 0
}
```

## Slowest row

- Run: `ordinary-5`
- Mode: `ordinary`
- Duration: `430.4 ms`
- Human clicks: `6`
- Core tool calls: `0`
