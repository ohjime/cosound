import os
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import asyncio
import random
from datetime import datetime
from pathlib import Path

import flet as ft
import pygame

from app.player import LayerManager
from app.client import (
    get_cosound,
    get_library,
    check_media,
)
from app.auth import authenticate, get_players


async def main(page: ft.Page):
    # 1. Page Configuration
    page.title = "Modern Music Player"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT

    # Set window size to mimic a phone/card UI
    page.window.width = 360
    page.window.height = 570

    # Restrict window resizing to prevent wonky layouts
    page.window.resizable = False
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True
    page.bgcolor = ft.Colors.TRANSPARENT
    page.window.bgcolor = ft.Colors.TRANSPARENT

    # Theme Colors based on the image
    BG_COLOR = ft.Colors.WHITE
    TEXT_PRIMARY = ft.Colors.BLACK
    TEXT_SECONDARY = ft.Colors.GREY_700
    ACCENT_COLOR = ft.Colors.GREY_800

    # Backend State
    player: LayerManager | None = None
    client_token: str | None = None
    player_token: str | None = None
    running = False

    # 2. UI Components

    # Console Output Area (read-only) - using ListView for auto-scroll
    console_output = ft.ListView(
        expand=True,
        spacing=0,
        auto_scroll=True,
    )

    output_container = ft.Container(
        content=console_output,
        bgcolor=ft.Colors.BLACK,
        padding=10,
        border_radius=ft.BorderRadius(
            top_left=20, top_right=20, bottom_left=0, bottom_right=0
        ),
        height=300,
        width=400,
        expand=True,
    )

    # Console Input Field
    console_input = ft.TextField(
        hint_text="Type command...",
        hint_style=ft.TextStyle(color=ft.Colors.GREY_600),
        text_style=ft.TextStyle(
            color=ft.Colors.GREEN_400,
            size=14,
            font_family="Courier New",
            weight=ft.FontWeight.W_200,
        ),
        bgcolor=ft.Colors.BLACK,
        border_color=ft.Colors.TRANSPARENT,
        focused_border_color=ft.Colors.TRANSPARENT,
        on_submit=None,  # Will be set after handle_command is defined
        expand=True,
        autofocus=True,
    )

    input_container = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text("$", color=ft.Colors.GREEN_400, size=14),
                console_input,
            ],
            spacing=5,
        ),
        bgcolor=ft.Colors.BLACK,
        padding=10,
        border_radius=ft.BorderRadius(
            top_left=0, top_right=0, bottom_left=20, bottom_right=20
        ),
    )

    # Login state management
    login_state = {
        "mode": "command",  # command, awaiting_email, awaiting_password, awaiting_client, awaiting_player
        "email": None,
        "password": None,
        "clients": {},  # Will be populated from API: {name: token}
        "players": {},  # Will be populated from API: {name: token}
        "client_names": [],  # Ordered list of client names
        "player_names": [],  # Ordered list of player names
    }

    def add_output(text: str):
        """Add text to console output, appending to ListView for auto-scroll"""
        console_output.controls.append(
            ft.Text(
                text,
                size=14,
                color=ft.Colors.GREEN_400,
                selectable=True,
                font_family="Courier New",
                weight=ft.FontWeight.W_200,
            )
        )

    def play_banner_sound() -> None:
        """Play the banner sound effect, if available.

        Uses pygame.mixer which is initialised in app.player.
        """
        try:
            assets_dir = Path(__file__).resolve().parent.parent / "assets"
            sound_path = assets_dir / "hiss.wav"
            if not sound_path.exists():
                return
            sound = pygame.mixer.Sound(str(sound_path))
            channel = pygame.mixer.find_channel()
            if channel:
                channel.play(sound)
        except Exception:
            # Fail silently if audio cannot be played
            pass

    def show_banner():
        """Display ASCII art and version, then play banner sound"""
        ascii_art = r"""
            /\_____/\
           /  o   o  \
          ( ==  ^  == ) 
           )         (
          (           )
         ( (  )   (  ) )
        (__(__)___(__)__)
        cosound CLI v1.00
"""

        for line in ascii_art.split("\n"):
            add_output(line)
        add_output("")
        play_banner_sound()

    time.sleep(0.6)
    # Add initial welcome message
    show_banner()

    # Cosound playback loop
    async def cosound_loop():
        nonlocal player, running
        while running:
            if client_token is None or player_token is None or player is None:
                await asyncio.sleep(1)
                continue
            try:
                add_output("Updating Cosound... 🤔")
                page.update()
                cosound = await asyncio.to_thread(
                    get_cosound, client_token, player_token
                )
                await asyncio.to_thread(
                    player.transition, cosound["soundscapes"], cosound["instrumental"]
                )
                random_emoji = random.choice(
                    ["😊", "😃", "😁", "🥳", "✨", "🚀", "💡", "🎉", "🤩", "🌟"]
                )
                add_output(f"Playing {random_emoji}")
                page.update()
                await asyncio.sleep(120)
            except Exception as ex:
                add_output(f"Error: {str(ex)[:30]} 😢")
                page.update()
                await asyncio.sleep(10)

    async def handle_command(e):
        nonlocal client_token, player_token, player, running
        command = console_input.value
        if not command.strip():
            return

        # Add command to output (mask password if in password mode)
        if login_state["mode"] == "awaiting_password":
            add_output(f"$ {'*' * len(command)}")
        else:
            add_output(f"$ {command}")

        # Process based on current state
        if login_state["mode"] == "command":
            if command.lower() == "login":
                add_output("Authentication Required.")
                add_output("")
                add_output("Email: ")
                login_state["mode"] = "awaiting_email"
            elif command.lower() == "help":
                add_output("Available commands:")
                add_output("  login  - Start authentication process")
                add_output("  clear  - Clear console")
                add_output("  help   - Show this help")
                add_output("")
            elif command.lower() == "clear":
                console_output.controls.clear()
            else:
                add_output(f"Unknown command: {command}")
                add_output("Type 'help' for available commands")
                add_output("")

        elif login_state["mode"] == "awaiting_email":
            login_state["email"] = command
            add_output("Password: ")
            login_state["mode"] = "awaiting_password"

        elif login_state["mode"] == "awaiting_password":
            login_state["password"] = command
            add_output("")
            add_output("Authenticating...")
            page.update()

            # Real API call to authenticate
            try:
                clients = await asyncio.to_thread(
                    authenticate, login_state["email"], login_state["password"]
                )
                if clients is None or len(clients) == 0:
                    add_output("Authentication failed. Try 'login' again.")
                    add_output("")
                    login_state["mode"] = "command"
                else:
                    login_state["clients"] = clients
                    login_state["client_names"] = list(clients.keys())
                    add_output("Authenticated! 😊")
                    add_output("")
                    add_output(f"Welcome, {login_state['email']}")
                    add_output("")
                    add_output("Select a Client Account:")
                    for i, client_name in enumerate(login_state["client_names"], 1):
                        add_output(f"  {i}. {client_name}")
                    add_output("")
                    add_output("Enter number: ")
                    login_state["mode"] = "awaiting_client"
            except Exception as ex:
                add_output(f"Error: {str(ex)[:40]}")
                add_output("")
                login_state["mode"] = "command"

        elif login_state["mode"] == "awaiting_client":
            try:
                choice = int(command)
                if 1 <= choice <= len(login_state["client_names"]):
                    selected_client_name = login_state["client_names"][choice - 1]
                    selected_client_token = login_state["clients"][selected_client_name]
                    add_output(f"{selected_client_name}")
                    add_output("")
                    add_output("Fetching Players...")
                    # Update client name display
                    client_name_display.value = selected_client_name
                    page.update()

                    # Real API call to get players
                    try:
                        players = await asyncio.to_thread(
                            get_players, str(selected_client_token)
                        )
                        if players is None or len(players) == 0:
                            add_output("No players found for this client.")
                            add_output("")
                            login_state["mode"] = "command"
                        else:
                            login_state["players"] = players
                            login_state["player_names"] = list(players.keys())
                            login_state["selected_client_token"] = selected_client_token
                            add_output("")
                            add_output("Select an available Player:")
                            for i, player_name in enumerate(
                                login_state["player_names"], 1
                            ):
                                add_output(f"  {i}. {player_name}")
                            add_output("")
                            add_output("Enter number: ")
                            login_state["mode"] = "awaiting_player"
                    except Exception as ex:
                        add_output(f"Error: {str(ex)[:40]}")
                        add_output("")
                        login_state["mode"] = "command"
                else:
                    add_output("Invalid selection. Try again: ")
            except ValueError:
                add_output("Please enter a number: ")

        elif login_state["mode"] == "awaiting_player":
            try:
                choice = int(command)
                if 1 <= choice <= len(login_state["player_names"]):
                    selected_player_name = login_state["player_names"][choice - 1]
                    # Update the nonlocal tokens
                    client_token = login_state["selected_client_token"]
                    player_token = login_state["players"][selected_player_name]
                    add_output(f"{selected_player_name}")
                    add_output("")

                    # Update player name display
                    player_name_display.value = selected_player_name
                    page.update()

                    # Check and download media
                    add_output("Checking media...")
                    page.update()

                    if check_media():
                        add_output("Media ready ✅")
                    else:
                        add_output("Downloading library... 📥")
                        page.update()
                        await asyncio.to_thread(
                            get_library, str(client_token), str(player_token)
                        )
                        add_output("Library downloaded ✅")

                    add_output("")
                    add_output("✅ Login complete!")
                    add_output("Starting player...")
                    page.update()

                    # Initialize player and start loop
                    player = LayerManager()
                    running = True
                    login_state["mode"] = "playing"

                    # Start the cosound loop
                    page.run_task(cosound_loop)

                    add_output("Connected to player.")
                    add_output("")
                else:
                    add_output("Invalid selection. Try again: ")
            except ValueError:
                add_output("Please enter a number: ")

        elif login_state["mode"] == "playing":
            if command.lower() == "stop":
                running = False
                add_output("Player stopped ⏹️")
                add_output("")
                login_state["mode"] = "command"
            elif command.lower() == "help":
                add_output("Available commands:")
                add_output("  stop   - Stop the player")
                add_output("  clear  - Clear console")
                add_output("  help   - Show this help")
                add_output("")
            elif command.lower() == "clear":
                console_output.controls.clear()
            else:
                add_output(f"Unknown command: {command}")
                add_output("Type 'help' for available commands")
                add_output("")

        # Clear input and update
        console_input.value = ""
        await console_input.focus()

    # Set the on_submit handler after function is defined
    console_input.on_submit = handle_command

    console = ft.Container(
        content=ft.Column(
            controls=[output_container, input_container],
            spacing=0,
        ),
        border=ft.Border.all(1, ft.Colors.GREY_700),
        border_radius=20,
        width=400,
    )

    # Reset button handler
    def reset_console(e):
        nonlocal running
        running = False  # Stop the player loop
        console_output.controls.clear()
        login_state["mode"] = "command"
        login_state["email"] = None
        login_state["password"] = None
        login_state["clients"] = {}
        login_state["players"] = {}
        login_state["client_names"] = []
        login_state["player_names"] = []
        show_banner()
        page.update()

    # Song Info (dynamic)
    client_name_display = ft.Text("Unauthenticated", size=12, color=TEXT_SECONDARY)
    player_name_display = ft.Text(
        "No Player Loaded",
        size=16,
        color=TEXT_PRIMARY,
        weight=ft.FontWeight.W_200,
    )
    player_info = ft.Row(
        controls=[
            ft.Column(
                controls=[client_name_display, player_name_display],
                spacing=2,
            ),
            ft.IconButton(
                icon=ft.Icons.RESTART_ALT,
                icon_color=TEXT_PRIMARY,
                tooltip="Cast Device",
                on_click=reset_console,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # Playback Controls
    # Helper to create the clean minimal buttons seen in the image
    def create_control_button(icon_name, size=24, color=TEXT_PRIMARY, on_click=None):
        return ft.IconButton(
            icon=icon_name,
            icon_size=size,
            icon_color=color,
            style=ft.ButtonStyle(
                overlay_color={ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT},
            ),
            on_click=on_click,
        )

    async def exit_app(e):
        await page.window.close()

    menubar = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Text(
                "cosound",
                size=24,
            ),
            create_control_button(
                ft.Icons.CIRCLE, 24, color=ft.Colors.RED_700, on_click=exit_app
            ),
        ],
        spacing=40,
    )

    # Volume Control Handler
    def on_volume_change(e):
        """Update pygame mixer volume when slider changes."""
        import pygame

        if pygame.mixer.get_init():
            # Convert 0-100 to 0.0-1.0
            volume = e.control.value / 100.0
            # Set volume for all channels
            for i in range(pygame.mixer.get_num_channels()):
                channel = pygame.mixer.Channel(i)
                if channel.get_busy():
                    channel.set_volume(volume)

    # Volume Control
    volume_slider = ft.Slider(
        min=0,
        max=100,
        value=30,
        active_color=ACCENT_COLOR,
        inactive_color=ft.Colors.GREY_300,
        thumb_color=ACCENT_COLOR,
        height=20,
        expand=True,
        on_change=on_volume_change,
    )

    volume_control = ft.Container(
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Icon(
                    ft.Icons.VOLUME_DOWN,
                    size=26,
                    color=TEXT_PRIMARY,
                ),
                volume_slider,
                ft.Icon(
                    ft.Icons.VOLUME_UP,
                    size=26,
                    color=TEXT_PRIMARY,
                ),
            ],
            spacing=0,
        ),
        padding=ft.Padding(left=20, right=20, top=0, bottom=0),
    )

    # 3. Main Layout Assembly
    # We wrap everything in a Container with white bg and rounded corners
    main_card = ft.Container(
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(height=4),  # Spacer at the top
                menubar,
                console,
                player_info,
                volume_control,
            ],
            scroll=ft.ScrollMode.HIDDEN,
        ),
        bgcolor=BG_COLOR,
        padding=ft.Padding(left=20, right=20, top=0, bottom=0),
        border_radius=18,
        expand=True,
    )

    # Wrap in WindowDragArea so the borderless window can be moved
    layout = ft.WindowDragArea(content=main_card, expand=True)

    page.add(layout)


if __name__ == "__main__":
    ft.run(main)
