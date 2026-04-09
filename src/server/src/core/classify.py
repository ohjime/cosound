import random
import numpy as np

sound_dimension = 5


def random_sound_classifier(
    sound_id: int,
    *args,
    **kwargs,
) -> list[float]:
    vector = np.zeros(sound_dimension)
    for i in range(sound_dimension):
        vector[i] = random.uniform(0, 1)
    return vector.tolist()


listener_dimension = 5


def random_listener_classifier(
    listener_id: int,
    *args,
    **kwargs,
) -> list[float]:
    vector = np.zeros(listener_dimension)
    for i in range(listener_dimension):
        vector[i] = random.uniform(0, 1)
    return vector.tolist()
