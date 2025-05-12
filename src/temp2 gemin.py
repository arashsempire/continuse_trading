import time
import threading
import collections
import random  # For simulating temperature readings


class BaseLogger:
    def _log(self, message):
        # Basic logging, can be replaced with Python's logging module
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]" +
              "{self.__class__.__name__}: {message}")


class DataCollector(BaseLogger):
    def __init__(self, history_size_seconds=90):
        # Keep a bit more than a minute's worth, adjust as needed
        super().__init__()
        # Store (timestamp, temperature) tuples.
        # Deque is thread-safe for append/pop from opposite ends, but iteration/indexed
        # access is not.
        # Hence, we'll use a lock for all operations for simplicity and safety here.
        self._temperature_history = collections.deque()
        self._lock = threading.Lock()
        # How long to keep data points
        self._history_max_age_seconds = history_size_seconds

        self._collecting = False
        self._collection_thread = None
        self._log("Initialized.")

    def _prune_old_data(self):
        """Removes data older than _history_max_age_seconds."""
        now = time.time()
        # Iterate safely: remove from left if condition met
        while self._temperature_history and self._temperature_history[0][0] < (
                now - self._history_max_age_seconds):
            now = time.time()  # ????? <===============================================
            self._temperature_history.popleft()

    def record_temperature(self, temp_value):
        timestamp = time.time()
        with self._lock:
            self._temperature_history.append((timestamp, temp_value))
            self._prune_old_data()  # Prune after adding new data
        self._log(f"Recorded temperature: {temp_value:.2f}°C" +
                  f"at {time.ctime(timestamp)}")

    def get_latest_temperature_data(self):
        """Returns the most recent (timestamp, temperature) tuple or None."""
        with self._lock:
            if not self._temperature_history:
                return None
            return self._temperature_history[-1]  # Last item is the newest

    def get_temperature_near_timestamp(self, target_timestamp, tolerance_seconds=10):
        """
        Finds a temperature reading near the target_timestamp.
        Iterates from newest to oldest.
        Returns (timestamp, temperature) or None.
        """
        with self._lock:
            if not self._temperature_history:
                return None
            # Search from newest to oldest for efficiency if recent data is more likely
            # Use a safe copy for iteration
            for ts, temp in reversed(self.get_all_history_safely()):
                if abs(ts - target_timestamp) <= tolerance_seconds:
                    return (ts, temp)
            # Fallback: if nothing in tolerance, find the closest one *before* or at
            # the target_timestamp
            closest_older_entry = None
            min_diff = float('inf')
            for ts, temp in reversed(self.get_all_history_safely()):
                if ts <= target_timestamp:
                    diff = target_timestamp - ts
                    if diff < min_diff :  # We want the one closest but not after
                        min_diff = diff
                        closest_older_entry = (ts, temp)
            return closest_older_entry

    def get_all_history_safely(self):
        """Returns a copy of the history for safe iteration."""
        with self._lock:
            return list(self._temperature_history)  # Return a copy

    def _collect_data_loop(self):
        self._log("Starting data collection loop...")
        while self._collecting:
            # Simulate irregular and frequent temperature gathering
            current_temp = random.uniform(18.0, 26.0)  # Example temperature
            self.record_temperature(current_temp)
            # Simulate irregular interval
            time.sleep(random.uniform(1, 5))  # e.g., every 1 to 5 seconds
        self._log("Data collection loop stopped.")

    def start_collection(self):
        if not self._collecting:
            self._collecting = True
            self._collection_thread = threading.Thread(target=self._collect_data_loop,
                                                       daemon=True)
            self._collection_thread.start()
            self._log("Data collection started.")
        else:
            self._log("Data collection already running.")

    def stop_collection(self):
        if self._collecting:
            self._collecting = False
            if self._collection_thread and self._collection_thread.is_alive():
                self._collection_thread.join()  # Wait for the thread to finish
            self._log("Data collection stopped.")


class DecisionMaker(BaseLogger):
    def __init__(self, data_collector: DataCollector, decision_interval_seconds=60):
        super().__init__()
        self.data_collector = data_collector
        self.decision_interval = decision_interval_seconds
        # Timestamp of data used in the *previous* decision
        self._last_decision_data_timestamp = None

        self._making_decisions = False
        self._decision_thread = None
        self._log("Initialized.")

    def _run_decision_logic(self):
        self._log("Running decision logic...")

        # 1. Get the last available data (most recent)
        current_data = self.data_collector.get_latest_temperature_data()
        if not current_data:
            self._log("No current temperature data available. Skipping decision.")
            return

        current_timestamp, current_temp = current_data
        self._log(f"Current data for decision: {current_temp:.2f}°C at" +
                  f" {time.ctime(current_timestamp)}")

        # 2. Get the data from the last cycle
        previous_cycle_data = None
        if self._last_decision_data_timestamp:
            # Try to get data that was current around the time of our last decision
            previous_cycle_data = self.data_collector.get_temperature_near_timestamp(
                self._last_decision_data_timestamp
            )
            if previous_cycle_data:
                prev_ts, prev_temp = previous_cycle_data
                self._log("Data from last cycle (near " +
                          f"{time.ctime(self._last_decision_data_timestamp)}): " +
                          f"{prev_temp:.2f}°C at {time.ctime(prev_ts)}")
            else:
                self._log("Could not find data near last cycle's timestamp (" +
                          f"{time.ctime(self._last_decision_data_timestamp)}).")
        else:
            self._log("First decision cycle, no previous cycle data to fetch.")

        # --- Your Actual Decision Logic Goes Here ---
        if previous_cycle_data:
            prev_ts, prev_temp = previous_cycle_data
            if current_temp > 24.0 and current_temp > prev_temp:
                self._log("DECISION: Temperature is high and rising. Action:" +
                          "Turn on AC.")
            elif current_temp < 20.0 and current_temp < prev_temp:
                self._log("DECISION: Temperature is low and falling. Action:" +
                          "Turn on Heater.")
            else:
                self._log("DECISION: Conditions stable or no specific action required" +
                          "based on current vs previous.")
        elif current_temp > 24.0 :
            self._log("DECISION (first run/no prev): Temperature is high. Action:" +
                      "Turn on AC.")
        elif current_temp < 20.0 :
            self._log("DECISION (first run/no prev): Temperature is low. Action:" +
                      "Turn on Heater.")
        else:
            self._log("DECISION (first run/no prev): Conditions appear normal.")
        # --- End of Decision Logic ---

        # IMPORTANT: Update the timestamp for the *next* cycle's "previous data"
        self._last_decision_data_timestamp = current_timestamp

    def _decision_loop(self):
        self._log("Starting decision-making loop...")
        while self._making_decisions:
            self._run_decision_logic()
            time.sleep(self.decision_interval)
        self._log("Decision-making loop stopped.")

    def start_making_decisions(self):
        if not self._making_decisions:
            self._making_decisions = True
            self._decision_thread = threading.Thread(
                target=self._decision_loop, daemon=True)
            self._decision_thread.start()
            self._log("Decision-making started.")
        else:
            self._log("Decision-making already running.")

    def stop_making_decisions(self):
        if self._making_decisions:
            self._making_decisions = False
            if self._decision_thread and self._decision_thread.is_alive():
                self._decision_thread.join()
            self._log("Decision-making stopped.")


# --- Example Usage ---
if __name__ == "__main__":
    collector = DataCollector(history_size_seconds=120)  # Keep 2 minutes of data
    decision_maker = DecisionMaker(
        data_collector=collector,
        decision_interval_seconds=10)  # Make decisions every 10s for demo

    try:
        collector.start_collection()
        decision_maker.start_making_decisions()

        # Keep the main thread alive for a while to see it in action
        # In a real application, this might be a server, a GUI loop, or another service.
        time.sleep(60)  # Run for 60 seconds

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        decision_maker.stop_making_decisions()
        collector.stop_collection()
        print("All processes stopped.")
