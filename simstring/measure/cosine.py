import math


class CosineMeasure:
    def similarity(self, left_features, right_features):
        if not left_features or not right_features:
            return 0.0

        intersection = len(left_features & right_features)
        denominator = math.sqrt(len(left_features) * len(right_features))
        if denominator == 0:
            return 0.0

        return intersection / denominator

