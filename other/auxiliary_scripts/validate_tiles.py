#!/usr/bin/env python3
"""
Validates the tile generation report produced by vec_tiles_gen.py.
Called by the CI workflow after tile generation to catch corrupt or empty outputs.
Exits with code 1 if any layer has a non-ok status.
"""

import json
import sys

REPORT_PATH = 'data/tiles/tile_generation_report.json'

with open(REPORT_PATH) as f:
    report = json.load(f)

errors = [(k, v) for k, v in report.items() if v.get('status') != 'ok']

if errors:
    for layername, info in errors:
        status = info.get('status', 'unknown')
        reason = info.get('reason', 'no reason given')
        print(f'  [{status.upper()}] {layername}: {reason}')
    sys.exit(1)

print('All layers OK.')
