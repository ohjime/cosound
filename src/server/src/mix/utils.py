from django.shortcuts import render


def generate_sound_artwork(sound):
    return "https://picsum.photos/seed/{}/400/400".format(sound.id)


def raise_alert(request, alert_msg, alert_type="alert-error"):
    response = render(
        request,
        "mix/index.html#alert",
        {
            "alert_type": alert_type,
            "alert_msg": alert_msg,
        },
    )
    response["HX-Retarget"] = "#mix_alerts"
    response["HX-Reswap"] = "afterbegin"
    return response
