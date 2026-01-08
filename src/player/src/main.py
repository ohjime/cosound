import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import time
import typer
import random
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console

from app.player import LayerManager
from app.client import get_cosound, get_library, login_and_get_tokens
from app.utils import delete_last_lines, print_ascii_banner, print_header

console = Console()


def main():
    typer.clear()
    print_ascii_banner()
    print_header()
    client_token, player_token = login_and_get_tokens()
    get_library(client_token, player_token)
    player = LayerManager()
    while True:
        with console.status(
            f"[bold cyan]Updating Cosound... 🤔[/bold cyan]", spinner="dots"
        ):
            min_duration_s = 3.0
            start = time.monotonic()
            cosound = get_cosound(client_token, player_token)
            player.transition(cosound)
            elapsed = time.monotonic() - start
            remaining = min_duration_s - elapsed
            if remaining > 0:
                time.sleep(remaining)
            random_emoji = random.choice(
                ["😊", "😃", "😁", "🥳", "✨", "🚀", "💡", "🎉", "🤩", "🌟"]
            )
        typer.secho(
            f"Cosound Updated {random_emoji} ({datetime.now().strftime('%b %d @ %I:%M:%S %p')}) \n",
            fg=typer.colors.BRIGHT_MAGENTA,
            bold=False,
        )
        time.sleep(120)
        delete_last_lines(2)


if __name__ == "__main__":
    main()
