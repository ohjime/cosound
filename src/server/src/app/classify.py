import random
import numpy as np

dim_v1 = 5


def classifier_v1(
    file,
) -> list[float]:
    vector = np.zeros(dim_v1)
    for i in range(dim_v1):
        vector[i] = random.uniform(0, 1)
    return vector.tolist()
