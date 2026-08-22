import random
import time

class AR1Wanderer:
    """Ornstein-Uhlenbeck (AR1) process for true organic stochastic wandering."""
    def __init__(self):
        self.states = {}

    def get(self, key: str, theta: float, sigma: float) -> float:
        if key not in self.states:
            self.states[key] = 0.0
        
        # x[t] = (1 - theta) * x[t-1] + noise
        self.states[key] = (1.0 - theta) * self.states[key] + random.gauss(0, sigma)
        return self.states[key]

# Global instance for bots to use
wanderer = AR1Wanderer()

class PoissonTimer:
    """Poisson process for true organic event triggering."""
    def __init__(self):
        self.next_time = 0.0
        self.active_until = 0.0

    def check(self, mean_interval_seconds: float, duration_min: float, duration_max: float) -> bool:
        now = time.time()
        
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
