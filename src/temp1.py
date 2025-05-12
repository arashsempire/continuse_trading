import BaseLogger


class DataStore:
    def __init__(self):
        self.data = []

    def add_data(self, data):
        self.data.append(data)

    def get_data(self):
        return self.data


class DataCollector(BaseLogger):
    def __init__(self, data_store):
        super().__init__()
        self.data_store = data_store

    def collect_data(self):
        # collect data
        data = []
        self.data_store.add_data(data)


class Decision(BaseLogger):
    def __init__(self, data_store):
        super().__init__()
        self.data_store = data_store

    def make_decision(self):
        data = self.data_store.get_data()
        # make decision based on data
        pass


# usage
data_store = DataStore()
data_collector = DataCollector(data_store)
decision = Decision(data_store)
data_collector.collect_data()
decision.make_decision()

# https://g.co/gemini/share/f1bde06cc9e0
