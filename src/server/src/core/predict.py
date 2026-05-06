import random
from collections import Counter
from django.tasks import task
from core.models import Player, Prediction, Sound
from vote.models import Vote
from mixer.models import SoundMix


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:

    player = Player.objects.get(pk=player_id)
    player_library = player.library()
    recent_votes = Vote.recent(player, minutes=30)
    active_listeners = Vote.get_listeners(recent_votes)
    currently_playing = player.playing
    next_prediction = Prediction.new()
    sound_score: Counter = Counter()

    for listener in active_listeners:
        listener_likes = listener.collected()
        for sound in listener_likes:
            if sound in player_library:
                sound_score[sound] += 1

    for listener in active_listeners:
        listener_mixes = SoundMix.collect(listener, recent=4)
        for mix in listener_mixes:
            for layer in mix.cosound.layering():
                sound_score[layer.sound] += 1

    for vote in recent_votes:
        match vote.value:
            case Vote.DOWNVOTE:
                for layer in vote.cosound.layering():
                    sound_score[layer.sound] -= 1
            case Vote.UPVOTE:
                for layer in vote.cosound.layering():
                    sound_score[layer.sound] += 1

    # Keep all currently playing sounds, shuffle to randomize tiebreaks, then
    # sort ascending so the 2 worst scorers are at the front.
    current_sounds: list[Sound] = [
        Sound.objects.get(pk=layer.sound_id) for layer in currently_playing.layers
    ]
    random.shuffle(current_sounds)
    current_sounds.sort(key=lambda s: sound_score[s])

    # Drop the 2 worst, carry the rest forward.
    keepers = current_sounds[1:]
    keeper_pks = {s.pk for s in keepers}

    # Fill the remaining slots with the top-scoring library sounds not already kept.
    needed = 3 - len(keepers)
    additions: list[Sound] = [
        s for s, _ in sound_score.most_common() if s.pk not in keeper_pks
    ][:needed]

    candidates = keepers + additions
    if len(candidates) < 3:
        candidate_pks = {s.pk for s in candidates}
        remaining = [s for s in player_library if s.pk not in candidate_pks]
        candidates += random.sample(remaining, min(3 - len(candidates), len(remaining)))

    for sound in candidates:
        next_prediction.add_layer(
            sound_id=sound.pk,
            gain=round(random.uniform(0.1, 0.4), 2),
        )

    if next_prediction:
        player.update(next_prediction)
        player.announce(next_prediction)
        return 1
    return 0
