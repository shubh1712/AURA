"""Deterministic simulation of hypothetical timeout configurations for AURA Phase 4.26 audit."""

def simulate_timeout_scenarios():
    scenarios = [
        {"name": "Current Baseline", "http_limit": 45.0, "op_ceiling": 60.0},
        {"name": "Scenario 1", "http_limit": 35.0, "op_ceiling": 60.0},
        {"name": "Scenario 2", "http_limit": 30.0, "op_ceiling": 60.0},
        {"name": "Scenario 3", "http_limit": 25.0, "op_ceiling": 60.0},
        {"name": "Scenario 4", "http_limit": 45.0, "op_ceiling": 75.0},
    ]

    initial_backoff = 0.5
    parent_deadline = 120.0
    stage1_duration = 15.915
    stage2_pre_mapping = 14.682 + 4.398  # requirements + search = 19.080s
    time_before_mapping = stage1_duration + stage2_pre_mapping  # 34.995s

    results = []
    print(f"{'Scenario':<18} | {'HTTP Lim':<8} | {'Op Ceil':<8} | {'Att 1 Max':<9} | {'Backoff':<7} | {'Rem for Att 2':<13} | {'Att 2 Max':<9} | {'Max Op Dur':<10} | {'Rem Parent DL':<13}")
    print("-" * 115)
    for s in scenarios:
        http_lim = s["http_limit"]
        op_ceil = s["op_ceiling"]

        # Attempt 1 duration if it times out
        att1_max = min(http_lim, op_ceil)
        # Backoff delay
        rem_after_att1 = op_ceil - att1_max
        backoff = min(initial_backoff, max(0.0, rem_after_att1))
        # Remaining time for attempt 2
        rem_for_att2 = max(0.0, rem_after_att1 - backoff)
        # Attempt 2 duration if admitted and times out
        att2_max = min(http_lim, rem_for_att2)
        # Total operation duration
        total_op_dur = att1_max + backoff + att2_max
        # Remaining parent deadline if mapping hits this max duration
        # (assuming 1 stalled worker exhausts total_op_dur)
        rem_parent = parent_deadline - (time_before_mapping + total_op_dur)

        print(f"{s['name']:<18} | {http_lim:>7.1f}s | {op_ceil:>7.1f}s | {att1_max:>8.1f}s | {backoff:>6.1f}s | {rem_for_att2:>12.1f}s | {att2_max:>8.1f}s | {total_op_dur:>9.1f}s | {rem_parent:>12.1f}s")
        results.append({
            "name": s["name"],
            "http_lim": http_lim,
            "op_ceil": op_ceil,
            "att1_max": att1_max,
            "backoff": backoff,
            "rem_for_att2": rem_for_att2,
            "att2_max": att2_max,
            "total_op_dur": total_op_dur,
            "rem_parent": rem_parent,
        })
    return results

if __name__ == "__main__":
    simulate_timeout_scenarios()
