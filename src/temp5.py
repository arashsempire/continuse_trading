import threading
import time


class BaseLogger:
    pass  # Base class logic here


class DataCollector(BaseLogger):
    def __init__(self, shared_data, data_lock):
        self.shared_data = shared_data
        self.data_lock = data_lock
        self.running = True

    def collect_data(self):
        while self.running:
            # Simulate temperature data collection
            temperature = self.get_temperature()
            timestamp = time.time()

            with self.data_lock:
                self.shared_data.append((timestamp, temperature))

            time.sleep(3)  # Simulate irregular data collection every few seconds

    def get_temperature(self):
        # Simulate temperature reading
        return 25.0 + (time.time() % 5)  # Example temperature value

    def stop(self):
        self.running = False


class DecisionMaker(BaseLogger):
    def __init__(self, shared_data, data_lock):
        self.shared_data = shared_data
        self.data_lock = data_lock

    def run_decision_logic(self):
        while True:
            time.sleep(60)  # Run every minute
            last_data = None
            previous_data = None

            with self.data_lock:
                if self.shared_data:
                    last_data = self.shared_data[-1]
                    previous_data = self.find_previous_data()

            # Run decision logic with the collected data
            print(f"Last Data: {last_data}, Previous Data: {previous_data}")

    def find_previous_data(self):
        # Simulate finding data from 1 minute ago
        # In a real implementation, use a more sophisticated approach
        return self.shared_data[-2] if len(self.shared_data) > 1 else None


# Shared data and lock
shared_data = []
data_lock = threading.Lock()

# Initialize classes
data_collector = DataCollector(shared_data, data_lock)
decision_maker = DecisionMaker(shared_data, data_lock)

# Run in separate threads
collector_thread = threading.Thread(target=data_collector.collect_data)
decision_thread = threading.Thread(target=decision_maker.run_decision_logic)

collector_thread.start()
decision_thread.start()

# Stop data collection after some time (for demonstration purposes)
time.sleep(300)
data_collector.stop()
collector_thread.join()
