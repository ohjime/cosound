import time

from django.contrib.auth import login, logout
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from core.models import Listener, User
from vote.adapters import UnifiedRequestLoginCodeForm
from vote.models import Vote
from vote.utils import (
    build_authenticated_vote_context,
    clear_login_state,
    get_login_state,
    generate_anon_email,
    generate_anon_username,
    get_throttle_seconds_left,
    get_vote_context,
    raise_alert,
    send_login_code,
)


def voter_index(request):
    return render(request, "vote/index.html", get_vote_context(request))


def check_auth(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    context = get_vote_context(request)
    if context["player"] == None:
        return render(request, "vote/index.html#help")

    context["is_swapped"] = request.htmx.target == "vote_card_body"

    if not request.user.is_authenticated:
        context["card_body"] = "vote/index.html#login_options"
        if context["is_swapped"]:
            return render(request, context["card_body"], context)
        return render(request, "vote/index.html#initial", context)

    context, time_left = build_authenticated_vote_context(request, request.user)
    context["card_body"] = (
        "vote/index.html#user_throttled"
        if time_left > 0
        else "vote/index.html#vote_ready"
    )
    context["is_swapped"] = request.htmx.target == "vote_card_body"

    if context["is_swapped"]:
        return render(request, context["card_body"], context)
    return render(request, "vote/index.html#initial", context)


def check_email(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    form = UnifiedRequestLoginCodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]

        try:
            send_login_code(request, email)
        except Exception:
            return raise_alert(
                request,
                alert_msg="Failed to send login code. Please try again later.",
                alert_type="alert-warning",
            )

        return render(request, "vote/index.html#enter_code")

    email_errors = form.errors.get("email")
    return raise_alert(
        request,
        alert_msg=(
            email_errors[0]
            if email_errors
            else "This email address can not be used with cosound."
        ),
        alert_type="alert-info",
    )


def check_code(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    email, correct_code = get_login_state(request)

    if not email or not correct_code:
        return raise_alert(
            request,
            alert_msg="Login session expired. Please request a new code.",
            alert_type="alert-warning",
        )

    if request.method == "POST":
        input_code = request.POST.get("code", "").strip()

        if input_code == str(correct_code):
            try:
                user = User.objects.get(email__iexact=email)
                Listener.objects.get_or_create(user=user)
                login(
                    request, user, backend="django.contrib.auth.backends.ModelBackend"
                )

                clear_login_state(request)

                context, time_left = build_authenticated_vote_context(
                    request, request.user
                )

                context["is_swapped"] = request.htmx.target == "vote_card_body"

                if time_left > 0:
                    return render(request, "vote/index.html#user_throttled", context)
                return render(request, "vote/index.html#vote_ready", context)
            except User.DoesNotExist:
                return raise_alert(
                    request,
                    alert_msg="User not found for this login code.",
                    alert_type="alert-error",
                )

    return raise_alert(
        request,
        alert_msg="Invalid or expired code.",
        alert_type="alert-error",
    )


def cancel_code(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    clear_login_state(request)
    return render(request, "vote/index.html#cancel_code")


def logout_session(request):
    if request.method != "POST":
        return HttpResponse("Request Denied.")

    logout(request)
    clear_login_state(request)

    redirect_url = reverse("vote:vote")
    query = request.GET.urlencode()
    if query:
        redirect_url = f"{redirect_url}?{query}"

    response = HttpResponse(status=204)
    response["HX-Redirect"] = redirect_url
    return response


def login_anonymously(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    time.sleep(2)

    try:
        username = generate_anon_username()
        user = User.objects.create_user(
            username=username,
            email=generate_anon_email(username),
            password=None,
        )
        user.set_unusable_password()
        user.save()
        Listener.objects.get_or_create(user=user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    except Exception:
        return raise_alert(
            request,
            alert_msg="Failed to Login Anonymously. Please try again later.",
            alert_type="alert-warning",
        )

    context, time_left = build_authenticated_vote_context(request, user)

    context["is_swapped"] = request.htmx.target == "vote_card_body"

    if time_left > 0:
        return render(request, "vote/index.html#user_throttled", context)
    return render(request, "vote/index.html#vote_ready", context)


def submit_vote(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    time.sleep(2)

    context = get_vote_context(request)
    player = context["player"]
    choice = context["choice"]

    if player is None or choice is None or not request.user.is_authenticated:
        return raise_alert(
            request,
            alert_msg="Unable to submit vote.",
            alert_type="alert-error",
        )

    listener, _ = Listener.objects.get_or_create(user=request.user)
    if get_throttle_seconds_left(listener) > 0:
        return raise_alert(
            request,
            alert_msg="You need to wait before voting again.",
            alert_type="alert-warning",
        )

    Vote.objects.create(
        voter=listener,
        player=player,
        cosound=player.playing,
        value=int(choice),
    )

    return render(request, "vote/index.html#vote_submitted")
