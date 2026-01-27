import random
import numpy as np

dim = 5


def random_classifier(
    file,
    *args,
    **kwargs,
) -> list[float]:
    vector = np.zeros(dim)
    for i in range(dim):
        vector[i] = random.uniform(0, 1)
    return vector.tolist()
