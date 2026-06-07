import json

runs = {
    'fast_track': 'outputs/runs/20260606T175234Z',
    'standard': 'outputs/runs/20260606T173845Z',
    'deep': 'outputs/runs/20260606T174650Z',
    'auto': 'outputs/runs/20260606T175411Z',
}

for name, path in runs.items():
    m = json.load(open(path + '/metadata.json', encoding='utf-8'))
    s = json.load(open(path + '/scorecard.json', encoding='utf-8'))
    t = m.get('token_usage', {})
    dur = m['duration_ms'] / 1000
    score = s['overall_score']
    passed = s['passed']
    action = s['recommended_next_action']
    tokens = t.get('total', 0)
    calls = t.get('total_calls', 0)
    print(f'=== {name.upper()} ===')
    print(f'  Duration: {dur:.1f}s')
    print(f'  Score: {score}/10 | Passed: {passed}')
    print(f'  Action: {action}')
    print(f'  Tokens: {tokens:,} | Calls: {calls}')
    dims = s.get('dimension_scores', {})
    for k, v in dims.items():
        print(f'    {k}: {v}')
    print()
