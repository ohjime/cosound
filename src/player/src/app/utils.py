import sys
import typer
from rich.text import Text
from rich.panel import Panel
from rich.console import Console
from rich.table import Table

the_love_life_you_wish_you_had = r"""
By the unknown artist
               ____
             _(____)_
    _____ooO_(_U__U_)_Ooo_____
   ____                    ____
"""

app = typer.Typer()
console = Console()


def print_cosound_state(cosound: dict):
    table = Table(
        title="Current CoSound State", show_header=True, header_style="bold magenta"
    )
    table.add_column("Sound ID", style="dim", width=12)
    table.add_column("Gain", justify="right")
    for sound_id, gain in cosound.items():
        table.add_row(sound_id, f"{gain:.2f}")
    console.print(table)


def print_ascii_banner() -> None:
    console.clear()
    try:
        typer.echo(the_love_life_you_wish_you_had.rstrip("\n"))
    except OSError:
        pass


def delete_last_lines(n: int = 1):
    CURSOR_UP = "\033[F"
    ERASE_LINE = "\033[K"
    for _ in range(n):
        sys.stdout.write(CURSOR_UP)
        sys.stdout.write(ERASE_LINE)


def print_header():
    content = Text(
        "C O  S   O   U  N D",
        justify="center",
        style="bold white",
    )
    panel = Panel(
        content,
        style="bold cyan",
        padding=(1, 6),
        title="[bold]  CLI Player ",
        subtitle=" v1.0.0 ",
        expand=False,
    )
    console.print(panel)
    console.print()


def get_or_read_api_key():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config["API_KEY"]
    except:
        api_key = input("Enter Player API Key:")
        return api_key


def read_current_manifest() -> dict:
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("MANIFEST", {})
    except:
        print("Config file not found.")
        return {}
