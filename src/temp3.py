import threading
import time
from collections import deque
from datetime import datetime


class BaseLogger:
    def __init__(self, shared):
        self.shared = shared  # shared = {"data": deque, "lock": threading.Lock()}


class DataCollector(BaseLogger):
    def start(self):
        # Start data collection in a background thread
        threading.Thread(target=self.collect_loop, daemon=True).start()

    def collect_loop(self):
        while True:
            temp = self.read_temperature()
            timestamp = datetime.now()
            with self.shared["lock"]:
                self.shared["data"].append((timestamp, temp))
            time.sleep(3)  # simulate irregular interval (change as needed)

    def read_temperature(self):
        # Replace with real sensor reading
        return 20 + (time.time() % 10)  # fake data


class DecisionMaker(BaseLogger):
    def run(self):
        while True:
            time.sleep(60)  # Run every 1 minute
            now = datetime.now()
            data_this_cycle = []
            one_minute_ago = now.timestamp() - 60
            with self.shared["lock"]:
                # Filter for data in the last cycle
                data_this_cycle = [d for (ts, d) in self.shared["data"]
                                   if one_minute_ago <= ts.timestamp() <= now.timestamp()]
            self.make_decision(data_this_cycle)

    def make_decision(self, recent_temps):
        if not recent_temps:
            print("No data available for this cycle.")
            return
        avg_temp = sum(recent_temps) / len(recent_temps)
        print(f"[{datetime.now()}] Avg temp in last minute: {avg_temp:.2f}°C")

# --- Initialization ---


shared = {
    "data": deque(maxlen=500),  # keep last N data points
    "lock": threading.Lock()
}

collector = DataCollector(shared)
decision_maker = DecisionMaker(shared)

collector.start()
decision_maker.run()  # blocks forever
