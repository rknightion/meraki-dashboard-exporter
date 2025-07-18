"""Profiling utilities for pprof-compatible output."""

from __future__ import annotations

import asyncio
import gc
import io
import sys
import threading
import time
import traceback
import tracemalloc
from collections import defaultdict
from datetime import datetime
from typing import Any

try:
    import cProfile
except ImportError:
    import profile as cProfile  # type: ignore[no-redef]  # noqa: N812

import psutil  # type: ignore[import-untyped]


class ProfilingUtils:
    """Utilities for generating profiling data in pprof-compatible format."""

    # Track exceptions for exception profiling
    _exception_counts: dict[str, int] = defaultdict(int)
    _exception_samples: dict[str, list[str]] = defaultdict(list)
    _profiling_start_time = time.time()
    _profiling_enabled = False

    @classmethod
    def _track_exception(cls, exc_type: type, exc_value: BaseException, exc_traceback: Any) -> None:
        """Track exceptions for profiling."""
        if exc_type is not None:
            key = f"{exc_type.__module__}.{exc_type.__name__}"
            cls._exception_counts[key] += 1
            # Store sample traceback (limit to 10 samples per exception type)
            if len(cls._exception_samples[key]) < 10:
                tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                cls._exception_samples[key].append("".join(tb_lines))

    @classmethod
    def enable_profiling(cls) -> None:
        """Enable memory profiling and exception tracking if not already enabled."""
        cls._profiling_enabled = True

        if not tracemalloc.is_tracing():
            tracemalloc.start(10)  # Store up to 10 frames

        # Install exception hook for tracking
        old_hook = sys.excepthook

        def exception_hook(exc_type: type, exc_value: BaseException, exc_traceback: Any) -> None:
            ProfilingUtils._track_exception(exc_type, exc_value, exc_traceback)
            old_hook(exc_type, exc_value, exc_traceback)

        sys.excepthook = exception_hook

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if profiling is enabled."""
        return cls._profiling_enabled

    @staticmethod
    def _profiling_disabled_message() -> str:
        """Return message when profiling is disabled."""
        return "# Profiling is disabled. Set MERAKI_EXPORTER_ENABLE_PROFILING=true to enable.\n"

    @classmethod
    def get_heap_profile(cls) -> str:
        """Generate a heap profile in pprof-compatible text format.

        Returns
        -------
        str
            Heap profile in pprof text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()

        # Force garbage collection to get accurate memory usage
        gc.collect()

        # Get current memory usage
        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics("filename")

            output.write("heap profile: 1: 1 [1: 1] @ heap/1\n")
            output.write("# heap profile\n\n")

            for stat in top_stats[:100]:  # Top 100 allocations
                output.write(
                    f"{stat.count}: {stat.size} [{stat.count}: {stat.size}] @ {stat.traceback}\n"
                )

            output.write("\n# runtime.MemStats\n")

        # Add general memory statistics
        process = psutil.Process()
        memory_info = process.memory_info()

        output.write(f"# Alloc = {memory_info.rss}\n")
        output.write(f"# TotalAlloc = {memory_info.rss}\n")
        output.write(f"# Sys = {memory_info.vms}\n")
        output.write("# Mallocs = 0\n")
        output.write("# Frees = 0\n")
        output.write(f"# HeapAlloc = {memory_info.rss}\n")
        output.write(f"# HeapSys = {memory_info.vms}\n")
        output.write("# HeapIdle = 0\n")
        output.write(f"# HeapInuse = {memory_info.rss}\n")
        output.write("# HeapReleased = 0\n")
        output.write("# HeapObjects = 0\n")

        return output.getvalue()

    @classmethod
    def get_allocs_profile(cls) -> str:
        """Generate an allocation profile in pprof-compatible text format.

        Returns
        -------
        str
            Allocation profile in pprof text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()

        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics("traceback")

            output.write("allocs profile: 1: 1 [1: 1] @ allocs\n")
            output.write("# allocs profile\n\n")

            for stat in top_stats[:100]:  # Top 100 allocation sites
                output.write(f"{stat.count}: {stat.size} [{stat.count}: {stat.size}] @")
                for frame in stat.traceback[:10]:  # Limit traceback depth
                    output.write(f" {frame.filename}:{frame.lineno}")
                output.write("\n")
        else:
            output.write("# tracemalloc not enabled\n")
            output.write("# Enable with PYTHONTRACEMALLOC=1 environment variable\n")

        return output.getvalue()

    @classmethod
    def get_inuse_objects_profile(cls) -> str:
        """Generate an in-use objects profile.

        Returns
        -------
        str
            In-use objects profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("inuse_objects profile\n")
        output.write("# Currently allocated objects by type\n\n")

        # Count objects by type
        obj_counts: dict[str, int] = defaultdict(int)
        for obj in gc.get_objects():
            obj_counts[type(obj).__name__] += 1

        # Sort by count
        sorted_counts = sorted(obj_counts.items(), key=lambda x: x[1], reverse=True)

        for type_name, count in sorted_counts[:50]:  # Top 50 types
            output.write(f"{count}: {type_name}\n")

        output.write(f"\n# Total objects: {sum(obj_counts.values())}\n")
        output.write(f"# Total types: {len(obj_counts)}\n")

        return output.getvalue()

    @classmethod
    def get_inuse_space_profile(cls) -> str:
        """Generate an in-use space profile.

        Returns
        -------
        str
            In-use space profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("inuse_space profile\n")
        output.write("# Memory usage by allocation site\n\n")

        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics("filename")

            total_size = sum(stat.size for stat in top_stats)

            for stat in top_stats[:50]:  # Top 50 by size
                percentage = (stat.size / total_size * 100) if total_size > 0 else 0
                output.write(
                    f"{stat.size:>10} bytes ({percentage:>5.1f}%) in {stat.count:>6} blocks: "
                    f"{stat.traceback}\n"
                )

            output.write(f"\n# Total allocated: {total_size} bytes\n")
        else:
            output.write("# tracemalloc not enabled\n")

        return output.getvalue()

    @classmethod
    async def get_cpu_profile(cls, duration: int = 30) -> bytes:
        """Generate a CPU profile for the specified duration.

        Parameters
        ----------
        duration : int
            Duration in seconds to profile (default 30).

        Returns
        -------
        bytes
            CPU profile in pprof binary format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message().encode("utf-8")

        # Create a profile
        pr = cProfile.Profile()

        # Start profiling
        pr.enable()

        # Wait for the specified duration
        await asyncio.sleep(duration)

        # Stop profiling
        pr.disable()

        # Convert to pprof format (simplified text format)
        output = io.StringIO()
        import pstats

        ps = pstats.Stats(pr, stream=output)
        ps.strip_dirs()
        ps.sort_stats("cumulative")
        ps.print_stats()

        # For now, return as text - in production you'd want to convert to actual pprof binary format
        return output.getvalue().encode("utf-8")

    @classmethod
    async def get_wall_profile(cls, duration: int = 30) -> str:
        """Generate a wall clock time profile.

        Parameters
        ----------
        duration : int
            Duration in seconds to profile (default 30).

        Returns
        -------
        str
            Wall time profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("wall profile\n")
        output.write(f"# Wall clock profile over {duration} seconds\n\n")

        # Sample thread activity over time
        samples: list[dict[str, Any]] = []
        start_time = time.time()

        # Take samples every 100ms
        sample_interval = 0.1
        num_samples = int(duration / sample_interval)

        for _ in range(num_samples):
            sample: dict[str, Any] = {
                "time": time.time() - start_time,
                "threads": {},
            }

            for thread in threading.enumerate():
                if thread.is_alive() and thread.ident is not None:
                    frame = sys._current_frames().get(thread.ident)
                    if frame:
                        sample["threads"][thread.name] = {
                            "file": frame.f_code.co_filename,
                            "line": frame.f_lineno,
                            "function": frame.f_code.co_name,
                        }

            samples.append(sample)
            await asyncio.sleep(sample_interval)

        # Aggregate by location
        location_times: dict[str, float] = defaultdict(float)
        for sample in samples:
            for thread_info in sample["threads"].values():
                location = (
                    f"{thread_info['file']}:{thread_info['line']} ({thread_info['function']})"
                )
                location_times[location] += sample_interval

        # Sort by time spent
        sorted_locations = sorted(location_times.items(), key=lambda x: x[1], reverse=True)

        for location, time_spent in sorted_locations[:50]:
            percentage = time_spent / duration * 100
            output.write(f"{time_spent:>6.1f}s ({percentage:>5.1f}%): {location}\n")

        return output.getvalue()

    @classmethod
    def get_goroutines_profile(cls) -> str:
        """Generate a goroutines-like profile showing all threads.

        Returns
        -------
        str
            Thread/goroutine profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("goroutine profile: total 0\n")

        # List all threads (Python equivalent of goroutines)
        for thread in threading.enumerate():
            output.write(f"\n# Thread: {thread.name} [{thread.ident}]\n")
            if hasattr(thread, "_target") and thread._target:
                output.write(f"# Target: {thread._target}\n")
            output.write(f"# Daemon: {thread.daemon}\n")
            output.write(f"# Alive: {thread.is_alive()}\n")

        # Add asyncio tasks information
        try:
            tasks = asyncio.all_tasks()
            output.write(f"\n# Asyncio tasks: {len(tasks)}\n")
            for i, task in enumerate(tasks):
                output.write(f"# Task {i}: {task.get_name()} - {task._state}\n")
        except RuntimeError:
            output.write("\n# Could not enumerate asyncio tasks\n")

        return output.getvalue()

    @classmethod
    def get_block_profile(cls) -> str:
        """Generate a blocking operations profile.

        Returns
        -------
        str
            Blocking profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("block profile\n")
        output.write("# Thread blocking analysis\n\n")

        # Analyze thread states
        blocked_threads = []
        for thread in threading.enumerate():
            if thread.ident is not None:
                frame = sys._current_frames().get(thread.ident)
            else:
                frame = None
            if frame:
                # Check if thread appears to be blocked
                code = frame.f_code
                if any(blocked in code.co_name for blocked in ["wait", "join", "acquire", "sleep"]):
                    blocked_threads.append({
                        "name": thread.name,
                        "location": f"{code.co_filename}:{frame.f_lineno}",
                        "function": code.co_name,
                    })

        output.write(f"# Potentially blocked threads: {len(blocked_threads)}\n")
        for thread_info in blocked_threads:
            output.write(
                f"Thread '{thread_info['name']}' blocked at {thread_info['location']} "
                f"in {thread_info['function']}\n"
            )

        # Add lock information
        output.write("\n# Active locks:\n")
        lock_type = type(threading.Lock())
        active_locks = [obj for obj in gc.get_objects() if isinstance(obj, lock_type)]
        locked_count = 0
        for lock in active_locks:
            try:
                if hasattr(lock, "locked") and lock.locked():
                    locked_count += 1
            except Exception:  # nosec B110
                # Some lock objects may not support locked() or may raise exceptions
                pass
        output.write(f"# Total locks: {len(active_locks)}, Locked: {locked_count}\n")

        return output.getvalue()

    @classmethod
    def get_mutex_profile(cls) -> str:
        """Generate a mutex (lock) contention profile.

        Returns
        -------
        str
            Mutex profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("mutex profile\n")
        output.write("# Lock contention analysis\n\n")

        # Find all Lock objects
        # threading.Lock and threading.RLock are factory functions, not types
        # We need to check the actual type of created lock objects
        lock_type = type(threading.Lock())
        rlock_type = type(threading.RLock())

        locks = []
        for obj in gc.get_objects():
            if isinstance(obj, (lock_type, rlock_type)):
                locks.append(obj)

        output.write(f"# Total locks found: {len(locks)}\n")

        # Check lock states
        locked_locks = 0
        for i, lock in enumerate(locks):
            try:
                if hasattr(lock, "locked") and lock.locked():
                    locked_locks += 1
                    output.write(f"Lock {i}: LOCKED\n")
            except Exception:  # nosec B110
                # Some lock objects may not support locked() or may raise exceptions
                # when checked. This is expected for certain lock types, so we skip them.
                pass

        output.write(f"\n# Locked: {locked_locks}, Unlocked: {len(locks) - locked_locks}\n")

        # Add threading synchronization primitives
        output.write("\n# Other synchronization primitives:\n")
        # Get the actual types since these are also factory functions
        condition_type = type(threading.Condition())
        event_type = type(threading.Event())
        semaphore_type = type(threading.Semaphore())

        conditions = [obj for obj in gc.get_objects() if isinstance(obj, condition_type)]
        events = [obj for obj in gc.get_objects() if isinstance(obj, event_type)]
        semaphores = [obj for obj in gc.get_objects() if isinstance(obj, semaphore_type)]

        output.write(f"# Conditions: {len(conditions)}\n")
        output.write(f"# Events: {len(events)}\n")
        output.write(f"# Semaphores: {len(semaphores)}\n")

        return output.getvalue()

    @classmethod
    def get_exceptions_profile(cls) -> str:
        """Generate an exceptions profile.

        Returns
        -------
        str
            Exceptions profile in text format.

        """
        if not cls._profiling_enabled:
            return cls._profiling_disabled_message()

        output = io.StringIO()
        output.write("exceptions profile\n")
        output.write(
            f"# Exception counts since {datetime.fromtimestamp(ProfilingUtils._profiling_start_time)}\n\n"
        )

        if not ProfilingUtils._exception_counts:
            output.write("# No exceptions recorded\n")
        else:
            # Sort by count
            sorted_exceptions = sorted(
                ProfilingUtils._exception_counts.items(), key=lambda x: x[1], reverse=True
            )

            for exc_type, count in sorted_exceptions:
                output.write(f"{count:>6}: {exc_type}\n")

                # Show sample tracebacks
                if exc_type in ProfilingUtils._exception_samples:
                    output.write("  Sample traceback:\n")
                    sample = ProfilingUtils._exception_samples[exc_type][0]
                    for line in sample.split("\n")[:10]:  # First 10 lines
                        if line.strip():
                            output.write(f"    {line}\n")
                    output.write("\n")

        output.write(f"\n# Total exceptions: {sum(ProfilingUtils._exception_counts.values())}\n")
        output.write(f"# Unique types: {len(ProfilingUtils._exception_counts)}\n")

        return output.getvalue()
