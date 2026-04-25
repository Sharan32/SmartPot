class DictDatabase:
    def __init__(self, feature_extractor):
        self.feature_extractor = feature_extractor
        self._strings = []

    def add(self, value):
        self._strings.append(value)

    def iter_strings(self):
        return iter(self._strings)

