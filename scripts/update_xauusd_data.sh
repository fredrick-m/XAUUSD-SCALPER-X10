#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/xauusd-scalper-x10}"
TARGET="${TARGET:-$APP_DIR/data/raw/XAUUSD_M1_DUKASCOPY_AUTO.csv}"
CACHE_DIR="${CACHE_DIR:-/opt/xauusd-data-cache/daily}"
LOCK_FILE="${LOCK_FILE:-/var/lock/xauusd-data-update.lock}"
SERVICE_NAME="${SERVICE_NAME:-xauusd-scalper-x10}"
export APP_DIR TARGET CACHE_DIR SERVICE_NAME

exec 9>"$LOCK_FILE"
flock -n 9 || { echo "another update is already running"; exit 0; }

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "missing project virtualenv: $APP_DIR/.venv/bin/python" >&2
  exit 1
fi
if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required (install nodejs/npm)" >&2
  exit 1
fi
if [[ ! -f "$TARGET" ]]; then
  echo "missing base dataset: $TARGET" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"
rm -f "$CACHE_DIR/XAUUSD_M1_RECENT.csv"

FROM=$("$APP_DIR/.venv/bin/python" - <<'PY'
import os
import pandas as pd
from pathlib import Path
p = Path(os.environ['TARGET'])
df = pd.read_csv(p, usecols=['time'], parse_dates=['time'])
last = pd.to_datetime(df['time']).max()
print((last - pd.Timedelta(days=7)).strftime('%Y-%m-%d'))
PY
)
TO=$(date -u +%F)

npx -y dukascopy-node \
  -i xauusd \
  -from "$FROM" \
  -to "$TO" \
  -t m1 \
  -p bid \
  -f csv \
  -dir "$CACHE_DIR" \
  -fn XAUUSD_M1_RECENT.csv \
  -r 3 \
  -rp 2000

RECENT="$CACHE_DIR/XAUUSD_M1_RECENT.csv"
[[ -s "$RECENT" ]] || { echo "download produced no data" >&2; exit 1; }

"$APP_DIR/.venv/bin/python" - <<'PY'
import os
import pandas as pd
from pathlib import Path

target = Path(os.environ['TARGET'])
recent = Path(os.environ['CACHE_DIR']) / 'XAUUSD_M1_RECENT.csv'

old = pd.read_csv(target, parse_dates=['time'])
old_rows = len(old)
old_last = pd.to_datetime(old['time']).max()

new = pd.read_csv(recent)
if 'timestamp' not in new.columns:
    raise SystemExit('recent dataset missing timestamp column')
new['time'] = pd.to_datetime(new['timestamp'], unit='ms', utc=True).dt.tz_localize(None)
new = new.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close'})
new['Volume'] = 1

keep = ['time','Open','High','Low','Close','Volume']
for c in keep:
    if c not in old.columns:
        old[c] = 1 if c == 'Volume' else pd.NA
for c in ('Open','High','Low','Close'):
    new[c] = pd.to_numeric(new[c], errors='coerce')

merged = pd.concat([old[keep], new[keep]], ignore_index=True)
merged = merged.dropna(subset=['time','Open','High','Low','Close'])
merged = merged.drop_duplicates(subset=['time'], keep='last').sort_values('time').reset_index(drop=True)

if len(merged) < old_rows:
    raise SystemExit(f'refusing shrink: {old_rows} -> {len(merged)}')
new_last = pd.to_datetime(merged['time']).max()
if new_last < old_last:
    raise SystemExit(f'refusing time regression: {old_last} -> {new_last}')
if not ((merged['High'] >= merged[['Open','Close','Low']].max(axis=1)) &
        (merged['Low'] <= merged[['Open','Close','High']].min(axis=1))).all():
    raise SystemExit('OHLC sanity check failed')

out = target.with_suffix('.tmp')
merged.to_csv(out, index=False)
out.replace(target)
print(f'rows {old_rows}->{len(merged)}; last {old_last} -> {new_last}')
PY

chown xauusd:xauusd "$TARGET"
systemctl restart "$SERVICE_NAME"
echo "update complete: $(date -Is)"
