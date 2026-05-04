from django import template

from core.utils import generate_random_stranger, generate_random_welcome

register = template.Library()


@register.simple_tag
def welcome_phrase():
    return generate_random_welcome()


@register.simple_tag
def stranger_phrase():
    return generate_random_stranger()
