class CharacterNgramFeatureExtractor:
    def __init__(self, n):
        self.n = n

    def features(self, text):
        if text is None:
            return []

        text = str(text)
        if len(text) < self.n:
            return [text] if text else []

        return [text[i:i + self.n] for i in range(len(text) - self.n + 1)]
