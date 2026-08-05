import random
from collections import Counter, defaultdict

from django.tasks import task

from core.models import Player, Prediction, Sound
from vote.models import Vote


def _predict_for_player(player_id: int) -> int:
    player = Player.objects.get(pk=player_id)
    recent_votes = Vote.recent(player, minutes=5)
    if not recent_votes:
        player.update(Prediction.new())
        return 0

    active_listeners = sorted(
        Vote.get_listeners(recent_votes),
        key=lambda listener: listener.pk,
    )
    next_prediction = Prediction.new()
    selected_sound_ids: set[int] = set()

    library_by_tag: dict[int, list[Sound]] = defaultdict(list)
    for sound in player.sounds.prefetch_related("tags"):
        for tag in sound.tags.all():
            library_by_tag[tag.pk].append(sound)

    for listener in active_listeners:
        tag_counts: Counter[int] = Counter()
        for sound in listener.collection.prefetch_related("tags"):
            tag_counts.update(tag.pk for tag in sound.tags.all())

        if not tag_counts:
            continue

        highest_count = max(tag_counts.values())
        usable_top_tags = [
            tag_id
            for tag_id, count in tag_counts.items()
            if count == highest_count and library_by_tag[tag_id]
        ]
        if not usable_top_tags:
            continue

        selected_tag = random.choice(usable_top_tags)
        unused_sounds = [
            sound
            for sound in library_by_tag[selected_tag]
            if sound.pk not in selected_sound_ids
        ]
        if not unused_sounds:
            continue

        selected_sound = random.choice(unused_sounds)
        next_prediction.add_layer(sound_id=selected_sound.pk, gain=1.0)
        selected_sound_ids.add(selected_sound.pk)

    if next_prediction:
        player.update(next_prediction)
        player.announce(next_prediction)
        return 1
    return 0


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    return _predict_for_player(player_id)
