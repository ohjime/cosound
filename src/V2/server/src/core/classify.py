import random
from abc import ABC, abstractmethod

import numpy as np


class SoundClassifier(ABC):

    dimension: int

    @staticmethod
    @abstractmethod
    def classify() -> list[float]:
        pass


class RandomSoundClassifier(SoundClassifier):
    dimension = 5

    @staticmethod
    def classify() -> list[float]:
        vector = np.zeros(RandomSoundClassifier.dimension)
        for i in range(RandomSoundClassifier.dimension):
            vector[i] = random.uniform(0, 1)
        return vector.tolist()
