# Profiling Support

The Meraki Dashboard Exporter includes comprehensive built-in profiling support with pprof-compatible endpoints for analyzing performance and resource usage.

## Enabling Profiling

Profiling is disabled by default to minimize overhead. To enable profiling, set the environment variable:

```bash
export MERAKI_EXPORTER_ENABLE_PROFILING=true
```

When profiling is disabled, all profiling endpoints will return a message indicating that profiling is disabled.

## Overview

When enabled, the exporter provides multiple profiling endpoints that can be used to analyze different aspects of application performance:

### Memory Profiling
- **Heap Profile**: `/debug/pprof/heap` - Current memory heap profile showing allocations
- **Allocations Profile**: `/debug/pprof/allocs` - Memory allocation statistics and sites
- **In-Use Objects**: `/debug/pprof/inuse_objects` - Currently allocated objects grouped by type
- **In-Use Space**: `/debug/pprof/inuse_space` - Memory usage by allocation site

### Performance Profiling
- **CPU Profile**: `/debug/pprof/profile?seconds=30` - CPU profiling for the specified duration (max 300s)
- **Wall Clock Profile**: `/debug/pprof/wall?seconds=30` - Wall time sampling showing where time is spent

### Concurrency Profiling
- **Thread/Goroutine Profile**: `/debug/pprof/goroutine` - Thread and async task information
- **Block Profile**: `/debug/pprof/block` - Thread blocking analysis
- **Mutex Profile**: `/debug/pprof/mutex` - Lock contention analysis

### Error Analysis
- **Exceptions Profile**: `/debug/pprof/exceptions` - Exception counts and sample tracebacks

## Using the Profiling Endpoints

### Manual Profiling

You can capture profiles for analysis using curl or your browser:

```bash
# Capture a 30-second CPU profile
curl http://localhost:9099/debug/pprof/profile?seconds=30 > cpu.pprof

# Capture heap profile
curl http://localhost:9099/debug/pprof/heap > heap.txt

# Capture allocation profile
curl http://localhost:9099/debug/pprof/allocs > allocs.txt

# View in-use objects
curl http://localhost:9099/debug/pprof/inuse_objects

# Capture wall clock profile
curl http://localhost:9099/debug/pprof/wall?seconds=30

# View exceptions
curl http://localhost:9099/debug/pprof/exceptions
```

### Integration with pprof Tools

While the profiles are in text format (not Go's binary pprof format), you can still analyze them:

```bash
# View heap profile
curl http://localhost:9099/debug/pprof/heap | less

# Monitor memory growth over time
watch -n 5 'curl -s http://localhost:9099/debug/pprof/heap | grep "# HeapAlloc"'

# Track object counts
watch -n 5 'curl -s http://localhost:9099/debug/pprof/inuse_objects | grep "# Total objects"'
```

### Continuous Profiling

For continuous profiling, you can set up a simple script:

```bash
#!/bin/bash
# capture_profiles.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROFILE_DIR="profiles/$TIMESTAMP"
mkdir -p "$PROFILE_DIR"

# Capture all profile types
curl -s http://localhost:9099/debug/pprof/heap > "$PROFILE_DIR/heap.txt"
curl -s http://localhost:9099/debug/pprof/allocs > "$PROFILE_DIR/allocs.txt"
curl -s http://localhost:9099/debug/pprof/inuse_objects > "$PROFILE_DIR/objects.txt"
curl -s http://localhost:9099/debug/pprof/inuse_space > "$PROFILE_DIR/space.txt"
curl -s http://localhost:9099/debug/pprof/goroutine > "$PROFILE_DIR/threads.txt"
curl -s http://localhost:9099/debug/pprof/block > "$PROFILE_DIR/blocks.txt"
curl -s http://localhost:9099/debug/pprof/mutex > "$PROFILE_DIR/mutex.txt"
curl -s http://localhost:9099/debug/pprof/exceptions > "$PROFILE_DIR/exceptions.txt"

# Capture CPU profile (30 seconds)
curl -s http://localhost:9099/debug/pprof/profile?seconds=30 > "$PROFILE_DIR/cpu.pprof" &

echo "Profiles saved to $PROFILE_DIR"
```

## Performance Considerations

- When profiling is enabled, memory profiling (tracemalloc) is automatically enabled on startup
- CPU profiling has minimal overhead but should not be run continuously
- Wall clock profiling samples every 100ms during the profiling period
- Exception tracking has negligible overhead
- All profiling endpoints are read-only and safe to use in production
- When profiling is disabled (default), there is zero overhead as no profiling code runs

## Profile Descriptions

### Heap Profile
Shows current memory allocations including:
- Number of allocations and size by file/line
- Total RSS (Resident Set Size) and VMS (Virtual Memory Size)
- Heap allocation statistics

### Allocations Profile
Provides detailed allocation statistics:
- Top allocation sites by count and size
- Full traceback for each allocation site
- Useful for finding memory leaks

### In-Use Objects Profile
Lists all Python objects currently in memory:
- Object counts by type (dict, list, str, etc.)
- Total object count and unique types
- Helpful for detecting object leaks

### In-Use Space Profile
Shows memory usage by allocation site:
- Memory size and percentage for each site
- Number of blocks allocated
- Total allocated memory

### CPU Profile
Standard cProfile output showing:
- Function call counts
- Time spent in each function
- Cumulative time including sub-calls

### Wall Clock Profile
Samples thread activity over time showing:
- Time spent in each code location
- Percentage of total wall time
- Useful for finding slow operations

### Thread/Goroutine Profile
Lists all threads and async tasks:
- Thread names and IDs
- Thread targets and daemon status
- Asyncio task names and states

### Block Profile
Analyzes blocking operations:
- Threads currently blocked
- Blocking function names (wait, join, acquire, sleep)
- Active lock counts

### Mutex Profile
Lock contention analysis:
- Total locks and their states
- Other synchronization primitives (conditions, events, semaphores)
- Useful for deadlock detection

### Exceptions Profile
Tracks all exceptions since startup:
- Exception counts by type
- Sample tracebacks for each exception type
- Total exceptions and unique types

## Landing Page

The exporter provides a user-friendly HTML landing page at `/` that displays:
- Exporter health status
- Current configuration
- Active collectors and their update tiers
- Links to all profiling endpoints
- Basic statistics (uptime, collector count, organizations)

## Docker Example

To run the exporter with profiling enabled in Docker:

```bash
docker run -e MERAKI_API_KEY=your_key -e MERAKI_EXPORTER_ENABLE_PROFILING=true -p 9099:9099 meraki-dashboard-exporter
```

## Troubleshooting

1. **All profiles return "Profiling is disabled"**: Ensure `MERAKI_EXPORTER_ENABLE_PROFILING=true` is set
2. **Memory profiling not working**: When profiling is enabled, tracemalloc is automatically started
3. **CPU profile is empty**: The application might not be doing enough work during profiling
4. **Exception profile is empty**: No exceptions have been raised since startup
5. **Wall profile shows only sleep**: Normal for an async application waiting for the next collection
6. **Profiling endpoints return 404**: Profiling endpoints are only registered when profiling is enabled
