import random
import time

class SimClock:
    """Clock abstraction that returns real wall-clock time in live mode,
    or simulated time in batch/export mode. This ensures Poisson anomaly
    timers fire correctly even when generating data in a tight loop."""
    def __init__(self):
        self._batch_mode = False
        self._simulated_time = 0.0

    def now(self) -> float:
        if self._batch_mode:
            return self._simulated_time
        return time.time()

    def advance(self, dt: float):
        """Advance simulated time by dt seconds. No-op in live mode."""
        if self._batch_mode:
            self._simulated_time += dt

    def set_batch_mode(self, start_time: float = None):
        """Switch to simulated time for batch data generation."""
        self._batch_mode = True
        self._simulated_time = start_time if start_time is not None else time.time()

    def set_live_mode(self):
        """Switch back to real wall-clock time (default)."""
        self._batch_mode = False

# Global clock instance
sim_clock = SimClock()

class AR1Wanderer:
    """Ornstein-Uhlenbeck (AR1) process for true organic stochastic wandering."""
    def __init__(self):
        self.states = {}
        self._tick_seen = set()

    def get(self, key: str, theta: float, sigma: float) -> float:
        if key not in self.states:
            self.states[key] = 0.0
            
        if key in self._tick_seen:
            raise RuntimeError(
                f"AR1Wanderer key '{key}' requested twice in the same tick - "
                f"this silently correlates two supposedly-independent signals. "
                f"Use a distinct key per physical quantity."
            )
        self._tick_seen.add(key)
        
        # x[t] = (1 - theta) * x[t-1] + noise
        self.states[key] = (1.0 - theta) * self.states[key] + random.gauss(0, sigma)
        return self.states[key]

    def end_tick(self):
        self._tick_seen.clear()

# Global instance for bots to use
wanderer = AR1Wanderer()

class PoissonTimer:
    """Poisson process for true organic event triggering."""
    def __init__(self):
        self.next_time = 0.0
        self.active_until = 0.0

    def check(self, mean_interval_seconds: float, duration_min: float, duration_max: float) -> bool:
        now = sim_clock.now()
        
        if now < self.active_until:
            return True # Event is actively occurring
            
        if self.next_time == 0.0:
            self.next_time = now + random.expovariate(1.0 / mean_interval_seconds)
            return False
            
        if now >= self.next_time:
            self.next_time = now + random.expovariate(1.0 / mean_interval_seconds)
            # using random.uniform here is fine because it determines a fixed duration for a single event, not tick-by-tick noise
            self.active_until = now + random.uniform(duration_min, duration_max)
            return True
            
        return False

