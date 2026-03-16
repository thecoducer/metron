# Memory Monitoring & OOM Debugging Guide

## Overview

Your application now has **memory monitoring automatically enabled** on startup. This helps detect memory issues **before** they cause OOM crashes that lose all logs.

## How It Works

### 1. **Periodic Memory Snapshots** (Every 60 seconds)
- Printed to `stderr` (survives OOM crashes)
- Format: `📊 MEMORY SNAPSHOT: XXX.XMB / 512MB (XX%)`
- **These will appear in Render's logs even if the app crashes**

### 2. **Memory Threshold Warnings**
- **75%+ of limit (384MB)**: Warning level logs (with 30s cooldown to avoid spam)
- **90%+ of limit (460MB)**: Critical level logs (immediate alert)
- Format: `⚠️  WARNING MEMORY: XXX.XMB (XX% of 512MB limit)`

### 3. **Per-Request Memory Tracking**
- Tracks memory delta for each HTTP request
- Logs if:
  - Request allocated >5MB of memory
  - Current usage >400MB
- Format: `Request: GET /api/endpoint | Time: 1.23s | Memory: 100.5→110.2MB (Δ9.7MB) | Used: 89%`

## What to Look For in Render Logs

### Normal Operation
```
📊 MEMORY SNAPSHOT: 120.5MB / 512MB (23%)
📊 MEMORY SNAPSHOT: 125.3MB / 512MB (24%)
Request: GET /api/portfolio | Time: 0.45s | Memory: 125.3→128.1MB (Δ2.8MB) | Used: 25%
```

### Warning Signs (Before OOM)
```
⚠️  WARNING MEMORY: 385.2MB (75% of 512MB limit)
Request: POST /sync | Time: 5.23s | Memory: 380.1→420.5MB (Δ40.4MB) | Used: 82%
⚠️  CRITICAL MEMORY: 465.3MB (91% of 512MB limit)
```

### OOM Crash Pattern (What You Saw)
```
📊 MEMORY SNAPSHOT: 450.0MB / 512MB (87%)
[no more output — process killed by kernel]
```

With the new monitoring, you'd now see:
```
📊 MEMORY SNAPSHOT: 450.0MB / 512MB (87%)
⚠️  CRITICAL MEMORY: 465.3MB (91% of 512MB limit)
[critical log message logged]
[process killed — but logs captured above]
```

## Debugging Steps

### Step 1: Identify Memory Leaks or Spikes

1. **Go to Render Logs** for your service
2. **Search for "MEMORY SNAPSHOT"** to see the timeline
3. **Look for the pattern**:
   - Slow increase → Memory leak (check broker_sync, cache, queues)
   - Sudden spike → Specific request causing issue (note the endpoint from logs)

### Step 2: Find the Culprit Endpoint

Search logs for the request that caused memory jump:
```
Request: POST /api/sync-portfolio | Time: 8.42s | Memory: 320→480MB (Δ160MB)
```

This endpoint allocated 160MB! Common causes:
- Fetching too much data from Zerodha/holding/market data
- Building large response without pagination
- Loading entire dataset into memory

### Step 3: Check Specific Services

Based on memory logs, check these areas:

**If spike happens during `/sync` endpoints:**
- [app/broker_sync.py](app/broker_sync.py) – Zerodha sync logic
- [app/api/zerodha_client.py](app/api/zerodha_client.py) – Data fetching

**If slow leak over time:**
- [app/cache.py](app/cache.py) – Unbounded cache growth
- Global variables or circular references preventing garbage collection
- Firebase connection pooling leaking memory

**If spike on `/statistics` or reporting:**
- High-precision calculations on large portfolios
- Holding lists with many securities

### Step 4: Use Local Production Build

Test locally with Gunicorn to replicate Render's environment:
```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run with same config as Render
gunicorn wsgi:app -c gunicorn.conf.py --log-level debug
```

Watch memory output locally while reproducing the issue.

## Implementation Details

### Files Added/Modified

- **[app/memory_monitor.py](app/memory_monitor.py)** - Core monitoring logic
  - `MemoryMonitor` class tracks RSS (Resident Set Size)
  - Periodic background thread emits snapshots
  - Threshold checks (75%, 90%)

- **[app/memory_tracking_middleware.py](app/memory_tracking_middleware.py)** - Request-level tracking
  - Records memory before/after each request
  - Logs delta and percentage for analysis

- **[wsgi.py](wsgi.py)** - Production entry point (updated)
  - Initializes monitoring on startup
  - Registers Flask middleware

- **[app/server.py](app/server.py)** - Development entry point (updated)
  - Also initializes monitoring for consistency

## Interpreting Memory Stats

```
📊 MEMORY SNAPSHOT: 245.3MB / 512MB (47%)
                    ^^^^^^              ^^
                    |                   └─ Percentage of 512MB limit
                    └─ Actual physical memory being used (RSS)
```

**RSS (Resident Set Size)** = Actual RAM consumed by your Python process
- Includes: Objects, caches, libraries, buffers
- Excludes: Swapped memory, memory shared with other processes

## Configuration

Default settings in [app/memory_monitor.py](app/memory_monitor.py):
- **Snapshot interval**: 60 seconds
- **Warning threshold**: 75% (384MB)
- **Critical threshold**: 90% (460MB)
- **Request log threshold**: >5MB delta or >400MB total

To customize, edit constants in [app/memory_monitor.py](app/memory_monitor.py):
```python
WARNING_THRESHOLD = int(MEMORY_LIMIT * 0.75)  # Change 0.75 to 0.70 for earlier warnings
MEMORY_LIMIT = 512 * 1024 * 1024  # Update if Render tier changes
```

## Optimization Tips

Once you identify the problematic code:

1. **Add pagination** to data-heavy endpoints
2. **Stream large responses** instead of building in memory
3. **Implement LRU cache** limits in [app/cache.py](app/cache.py)
4. **Process data incrementally** (generator instead of list)
5. **Clear caches** after broker sync completes
6. **Monitor connection pools** (Firebase, Zerodha)

Example optimization:
```python
# Before (memory spike)
holdings = fetch_all_holdings()  # Loads everything
return jsonify([h.to_dict() for h in holdings])

# After (streaming)
def stream_holdings():
    for holding in fetch_holdings_batch():
        yield json.dumps(holding.to_dict()) + '\n'
return stream_holdings()
```

## Next Steps

1. **Deploy** the monitoring code
2. **Wait for next incident** (or trigger one with load testing)
3. **Check Render logs** after memory spike
4. **Identify the endpoint** from memory delta logs
5. **Optimize that endpoint** based on findings

## Still Stuck?

If memory continues spiking without clear causes:
1. Add detailed logging in peak-memory endpoints
2. Check for circular references (e.g., cache entries holding entire objects)
3. Consider upgrading tier temporarily to trace the issue
4. Use `memory_profiler` library locally on suspected functions
