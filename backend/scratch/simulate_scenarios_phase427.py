"""Deterministic simulation script for Phase 4.27 timeout scenarios."""

def run_simulations():
    scenarios = [
        {
            "name": "Scenario 1: First attempt succeeds in 20s",
            "att1_actual": 20.0,
            "att2_actual": None,
            "parent_remaining": 120.0,
        },
        {
            "name": "Scenario 2: First attempt succeeds in 28s",
            "att1_actual": 28.0,
            "att2_actual": None,
            "parent_remaining": 120.0,
        },
        {
            "name": "Scenario 3: First attempt would succeed in 35s (premature cancellation)",
            "att1_actual": 35.0,
            "att2_actual": 35.0,  # If retry also needs 35s
            "parent_remaining": 120.0,
        },
        {
            "name": "Scenario 4: First attempt stalls (timeout), second succeeds in 20s",
            "att1_actual": float("inf"),  # stalls
            "att2_actual": 20.0,
            "parent_remaining": 120.0,
        },
        {
            "name": "Scenario 5: Two attempts both time out",
            "att1_actual": float("inf"),
            "att2_actual": float("inf"),
            "parent_remaining": 120.0,
        },
        {
            "name": "Scenario 6: Parent deadline exhaustion during retry (40s parent budget)",
            "att1_actual": float("inf"),
            "att2_actual": 15.0,
            "parent_remaining": 40.0,
        },
    ]

    configs = [
        {"name": "Baseline (45.0s)", "timeout_seconds": 45.0, "op_ceiling": 60.0},
        {"name": "Phase 4.27 (30.0s)", "timeout_seconds": 30.0, "op_ceiling": 60.0},
    ]

    backoff_seconds = 0.5

    for sc in scenarios:
        print(f"\n=======================================================")
        print(f"=== {sc['name']}")
        print(f"=======================================================")
        for cfg in configs:
            t_sec = cfg["timeout_seconds"]
            op_ceil = cfg["op_ceiling"]
            parent_rem = sc["parent_remaining"]
            effective_op_deadline = min(op_ceil, parent_rem)

            # Attempt 1
            rem1 = effective_op_deadline
            http1 = min(t_sec, rem1)
            actual1 = sc["att1_actual"]

            if actual1 <= http1:
                # Success on attempt 1
                dur = actual1
                status = f"SUCCESS (Attempt 1 in {dur:.1f}s)"
                source = None
            else:
                # Attempt 1 times out or hits deadline
                att1_dur = http1
                elapsed = att1_dur
                rem_after_att1 = effective_op_deadline - elapsed
                if rem_after_att1 <= 0:
                    status = f"FAILED (Attempt 1 timed out after {elapsed:.1f}s, budget exhausted)"
                    dur = elapsed
                else:
                    # Backoff
                    backoff = min(backoff_seconds, rem_after_att1)
                    elapsed += backoff
                    rem_after_backoff = effective_op_deadline - elapsed
                    if rem_after_backoff <= 0:
                        status = f"FAILED (Backoff exhausted budget at {elapsed:.1f}s)"
                        dur = elapsed
                    else:
                        # Attempt 2
                        http2 = min(t_sec, rem_after_backoff)
                        actual2 = sc["att2_actual"]
                        if actual2 <= http2:
                            elapsed += actual2
                            status = f"SUCCESS (Attempt 2 in {actual2:.1f}s, total {elapsed:.1f}s)"
                            dur = elapsed
                        else:
                            elapsed += http2
                            status = f"FAILED (Attempt 2 timed out after {http2:.1f}s, total {elapsed:.1f}s)"
                            dur = elapsed
            print(f"[{cfg['name']}]: {status} | Att 1 budget={http1:.1f}s | Op budget remaining={max(0.0, effective_op_deadline - dur):.1f}s")

if __name__ == "__main__":
    run_simulations()
