class Searcher:
    def __init__(self, database, measure):
        self.database = database
        self.measure = measure

    def search(self, query, threshold):
        query_features = set(self.database.feature_extractor.features(query))
        matches = []

        for candidate in self.database.iter_strings():
            candidate_features = set(self.database.feature_extractor.features(candidate))
            score = self.measure.similarity(query_features, candidate_features)
            if score >= threshold:
                matches.append(candidate)

        return matches

