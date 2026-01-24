import sys
import typer
from rich.text import Text
from rich.panel import Panel
from rich.console import Console

the_love_life_you_wish_you_had = r"""
By the unknown artist
      |       |        |       | |
 ' |   |   |     '  |      '      
              |           |     | 
 '     |  _,..--I--..,_ |         
   / _.-`` _,-`   `-,_ ``-._ \ lt.
     `-,_,_,.,_   _,.,_._,-`      
|  | '   '     `Y` __ '     '     
  '|        ,-. I /  \       |  | 
 |    |    /   )I \  /     '   |  
'  '      /   / I_.""._           
|  |    ,l  .'..`      `.   ' |  |
 |     / | /   \        l         
      /, '"  .  \      ||   |   | 
 |  ' ||      |"|      ||   |     
'     ||      | |      ||       | 
|     \|      | '.____,'/  |  |   
   |   |      |  |    |F   '    | 
 | '   |      |  | |\ |     ' |   
       |      |  | || |      |    
|  |   |      |  | || |    |    | 
       |      |  | || |      |    
 ' |   '.____,'  \_||_/   |    |  
         |/\|    [_][_]      |    
"""

app = typer.Typer()
console = Console()


def print_ascii_banner() -> None:
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
        "C O  S  O   U  N  D S",
        justify="center",
        style="bold white",
    )
    panel = Panel(
        content,
        style="bold cyan",
        padding=(1, 6),
        title="[bold]CLI Player",
        subtitle="v1.0.0",
        expand=False,
    )
    console.print(panel)
    console.print()
