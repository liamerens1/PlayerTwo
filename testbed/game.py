"""The Ursina front end: draws the world, reads the keyboard and mouse, runs episodes.

The only module that imports Ursina (lazily, inside `run_game`), so everything else in the
testbed imports and tests without it. Ursina ships no type information, so its objects
are typed `Any` here.

Controls (match profiles/simple-walker.yaml and profiles/testbed.yaml): W/S forward/back,
A/D strafe, mouse X to turn, Escape quits. The episode clock pauses while the window
isn't focused, so alt-tabbing (or starting PlayerTwo from a terminal) costs no time.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from testbed.autopilot import Autopilot
from testbed.cursor import MouseLook
from testbed.episode import Episode, Outcome
from testbed.levels import TARGET_SIZE, generate_layout
from testbed.physics import PLAYER_RADIUS, PlayerState, start_state, step
from testbed.results import ResultsLog
from testbed.world import Rect, ground_tiles

logger = logging.getLogger(__name__)

WINDOW_TITLE = "PlayerTwo Testbed"
WINDOW_SIZE = (1280, 720)
FPS_CAP = 60
TURN_DEGREES_PER_PIXEL = 0.1
"""Mouse sensitivity. Windows pointer acceleration doubles a fast move: PlayerTwo's
injected 150 px arrives as about 306 px on Liam's machine (measured live), so this makes a
turn about 30 degrees. On a machine without acceleration a turn is about 15 degrees."""
BANNER_SECONDS = 2.0
FALL_SECONDS = 0.8
"""How long the falling animation plays before the YOU FELL banner."""
SCREENSHOT_DELAY_SECONDS = 0.5
CHECKER_SIZE = 2.0
"""World units per ground square."""

CAMERA_DISTANCE = 7.0
CAMERA_HEIGHT = 4.0
CAMERA_LOOK_AHEAD = 3.0
CAMERA_FOV = 60
CAMERA_PITCH = math.degrees(math.atan2(CAMERA_HEIGHT - 1.0, CAMERA_DISTANCE + CAMERA_LOOK_AHEAD))
"""Looking down at a point CAMERA_LOOK_AHEAD in front of the player, 1 unit up."""

# Colours (RGB 0-255), chosen to stay distinct at 640 px for a small vision model.
SKY = (135, 195, 245)
GROUND_A = (70, 150, 60)
GROUND_B = (95, 175, 80)
FENCE = (235, 235, 235)
WALL = (95, 80, 120)
TARGET = (255, 220, 0)
PLAYER = (40, 90, 220)
EDGE = (220, 50, 40)
VOID = (25, 25, 40)
BANNER = {
    Outcome.SUCCESS: (30, 160, 60),
    Outcome.FELL: (190, 40, 40),
    Outcome.TIMEOUT: (200, 120, 20),
}


@dataclass(frozen=True)
class GameOptions:
    level: int
    seed: int
    episodes: int
    timeout_seconds: float | None
    results_path: Path
    tag: str = ""
    autopilot: bool = False
    screenshot_dir: Path | None = None


def run_game(options: GameOptions) -> None:
    """Open the window and play `options.episodes` episodes, then close."""
    TestbedGame(options).run()


class TestbedGame:
    def __init__(self, options: GameOptions) -> None:
        self.options = options
        self.results = ResultsLog(options.results_path)
        self.episode_index = 0
        self.episode: Episode | None = None
        self.state: PlayerState | None = None
        self.autopilot: Autopilot | None = None
        self.banner_left = 0.0
        self.fall_left = 0.0
        self.fall_depth = 0.0
        self.screenshot_left: float | None = None
        self.had_focus: bool | None = None  # None: not checked yet
        self.mouse_look: MouseLook | None = None
        self.u: Any = None  # the ursina module
        self.app: Any = None
        self.level_entities: list[Any] = []

    # ------------------------------------------------------------------ setup

    def run(self) -> None:
        import ursina
        from panda3d.core import ClockObject, WindowProperties

        self.u = ursina
        self.app = ursina.Ursina(
            title=WINDOW_TITLE,
            size=WINDOW_SIZE,
            fullscreen=False,
            borderless=False,
            vsync=False,
            development_mode=False,
            editor_ui_enabled=False,
        )
        clock = ClockObject.getGlobalClock()
        clock.setMode(ClockObject.MLimited)
        clock.setFrameRate(FPS_CAP)
        fixed = WindowProperties()
        fixed.setFixedSize(True)
        self.app.win.requestProperties(fixed)
        window = ursina.window
        window.title = WINDOW_TITLE
        window.color = self._color(SKY)
        # Ursina's own hotkeys: F12 toggles its editor UI, F11 fullscreen, F10 render
        # modes. F12 is PlayerTwo's kill switch, so switch them all off.
        window.input_entity.enabled = False
        for counter in ("fps_counter", "entity_counter", "collider_counter"):
            widget = getattr(window, counter, None)
            if widget is not None:
                widget.enabled = False
        ursina.camera.fov = CAMERA_FOV

        self._build_static_ui()
        ticker = ursina.Entity()
        ticker.update = self._update
        ticker.input = self._input
        self._start_episode()
        self.app.run()

    def _color(self, rgb: tuple[int, int, int], alpha: int = 255) -> Any:
        return self.u.color.rgba32(*rgb, alpha)

    def _build_static_ui(self) -> None:
        u = self.u
        self.player_body = u.Entity(
            model=u.Cylinder(resolution=16, radius=PLAYER_RADIUS, height=1.2),
            color=self._color(PLAYER),
            shader=u.shaders.basic_lighting_shader,
        )
        self.player_head = u.Entity(
            parent=self.player_body,
            model="sphere",
            y=1.5,
            scale=0.7,
            color=self._color(PLAYER),
            shader=u.shaders.basic_lighting_shader,
        )
        # A white nose so the facing direction is visible.
        u.Entity(parent=self.player_head, model="cube", z=0.5, scale=0.3, color=u.color.white)
        u.Entity(  # the void below the world
            model="plane", y=-30, scale=400, color=self._color(VOID)
        )
        self.hud = u.Text(
            text="",
            parent=u.camera.ui,
            position=u.window.top_left + u.Vec2(0.02, -0.02),
            scale=1.6,
            color=u.color.black,
        )
        self.clock_text = u.Text(
            text="",
            parent=u.camera.ui,
            position=u.window.top_right + u.Vec2(-0.02, -0.02),
            origin=(0.5, 0.5),
            scale=1.6,
            color=u.color.black,
        )
        self.overlay = u.Entity(
            parent=u.camera.ui, model="quad", scale=(4, 2), z=-1, color=u.color.clear
        )
        self.overlay_text = u.Text(
            text="", parent=u.camera.ui, origin=(0, 0), scale=6, z=-2, color=u.color.white
        )
        self.overlay.enabled = self.overlay_text.enabled = False

    def _build_level(self) -> None:
        u = self.u
        for entity in self.level_entities:
            u.destroy(entity)
        self.level_entities = []
        assert self.episode is not None
        layout = self.episode.layout
        for tile in ground_tiles(layout.platform, layout.pit):
            self._slab(tile, -0.5, 1.0, GROUND_A, texture=self._checker_texture(tile))
        if layout.fenced:
            p = layout.platform
            for rect in (
                Rect(p.min_x - 0.3, p.min_z - 0.3, p.max_x + 0.3, p.min_z),
                Rect(p.min_x - 0.3, p.max_z, p.max_x + 0.3, p.max_z + 0.3),
                Rect(p.min_x - 0.3, p.min_z, p.min_x, p.max_z),
                Rect(p.max_x, p.min_z, p.max_x + 0.3, p.max_z),
            ):
                self._slab(rect, 0.4, 0.8, FENCE)
        else:
            self._edge_stripes(layout.platform, inside=True)
        if layout.pit is not None:
            self._edge_stripes(layout.pit, inside=False)
        for box in layout.obstacles:
            self._slab(box, layout.obstacle_height / 2, layout.obstacle_height, WALL)
        tx, tz = layout.target.center
        self.target = u.Entity(
            model="cube",
            position=(tx, TARGET_SIZE / 2, tz),
            scale=TARGET_SIZE,
            color=self._color(TARGET),
            unlit=True,
        )
        self.level_entities.append(self.target)

    def _slab(
        self,
        rect: Rect,
        y: float,
        height: float,
        rgb: tuple[int, int, int],
        texture: Any = None,
    ) -> None:
        u = self.u
        cx, cz = rect.center
        entity = u.Entity(
            model="cube",
            position=(cx, y, cz),
            scale=(rect.width, height, rect.depth),
            color=u.color.white if texture is not None else self._color(rgb),
            shader=u.shaders.basic_lighting_shader,
        )
        if texture is not None:
            entity.texture = texture
        self.level_entities.append(entity)

    def _edge_stripes(self, rect: Rect, inside: bool) -> None:
        """Red stripes on the ground along a deadly edge (inside the platform's edge, or
        around the rim of the pit)."""
        w = 0.4
        if inside:
            strips = [
                Rect(rect.min_x, rect.min_z, rect.max_x, rect.min_z + w),
                Rect(rect.min_x, rect.max_z - w, rect.max_x, rect.max_z),
                Rect(rect.min_x, rect.min_z, rect.min_x + w, rect.max_z),
                Rect(rect.max_x - w, rect.min_z, rect.max_x, rect.max_z),
            ]
        else:
            strips = [
                Rect(rect.min_x - w, rect.min_z - w, rect.max_x + w, rect.min_z),
                Rect(rect.min_x - w, rect.max_z, rect.max_x + w, rect.max_z + w),
                Rect(rect.min_x - w, rect.min_z, rect.min_x, rect.max_z),
                Rect(rect.max_x, rect.min_z, rect.max_x + w, rect.max_z),
            ]
        for strip in strips:
            self._slab(strip, 0.01, 0.02, EDGE)

    def _checker_texture(self, tile: Rect) -> Any:
        """Squares of CHECKER_SIZE, one texture pixel each, aligned to world coordinates so
        tiles around a pit line up. Moving over them is what makes motion visible."""
        from PIL import Image

        cols = max(1, math.ceil(tile.width / CHECKER_SIZE))
        rows = max(1, math.ceil(tile.depth / CHECKER_SIZE))
        image = Image.new("RGB", (cols, rows), GROUND_A)
        for col in range(cols):
            for row in range(rows):
                x = math.floor(tile.min_x / CHECKER_SIZE) + col
                z = math.floor(tile.min_z / CHECKER_SIZE) + row
                if (x + z) % 2:
                    image.putpixel((col, rows - 1 - row), GROUND_B)  # image rows run top-down
        texture = self.u.Texture(image)
        texture.filtering = None
        return texture

    # ------------------------------------------------------------------ episodes

    def _start_episode(self) -> None:
        seed = self.options.seed + self.episode_index
        layout = generate_layout(self.options.level, seed, self.options.timeout_seconds)
        self.episode = Episode(layout)
        self.state = start_state(layout)
        self.autopilot = Autopilot(layout) if self.options.autopilot else None
        self.fall_left = 0.0
        self.fall_depth = 0.0
        self._build_level()
        self.hud.text = f"Level {layout.level}: Reach the yellow cube"
        self.clock_text.text = f"{math.ceil(layout.timeout_seconds)} s"
        if self.options.screenshot_dir is not None:
            self.screenshot_left = SCREENSHOT_DELAY_SECONDS
        self._sync_view()
        logger.info("episode %d: level %d seed %d", self.episode_index + 1, layout.level, seed)

    def _end_episode(self, outcome: Outcome) -> None:
        assert self.episode is not None
        result = self.episode.result(
            episode=self.episode_index + 1,
            tag=self.options.tag,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.results.append(result)
        print(
            f"episode {result.episode}: {outcome.value} in {result.seconds:.1f} s "
            f"(seed {result.seed}, closest {result.closest_distance:.2f})",
            flush=True,
        )
        self.overlay.color = self._color(BANNER[outcome], 235)
        self.overlay_text.text = outcome.banner
        self.overlay_text.scale = 6
        self.overlay.enabled = self.overlay_text.enabled = True
        self.banner_left = BANNER_SECONDS

    # ------------------------------------------------------------------ per frame

    def _focused(self) -> bool:
        if self.mouse_look is None:
            self.mouse_look = MouseLook(self.app.win.getWindowHandle().getIntHandle())
        return self.mouse_look.focused()

    def _update(self) -> None:
        u = self.u
        dt = min(u.time.dt, 0.1)
        assert self.episode is not None and self.state is not None
        self.target.rotation_y += 40 * dt

        if self.screenshot_left is not None:  # hold the start view until it's saved
            self.screenshot_left -= dt
            if self.screenshot_left <= 0:
                self._save_screenshot()
                self.screenshot_left = None
            return

        if self.banner_left > 0:
            self.banner_left -= dt
            if self.banner_left <= 0:
                self.overlay.enabled = self.overlay_text.enabled = False
                self.episode_index += 1
                if self.episode_index >= self.options.episodes:
                    self._quit()
                    return
                self._start_episode()
            return

        if self.fall_left > 0:
            self.fall_left -= dt
            self.fall_depth += 12 * dt
            self._sync_view()
            if self.fall_left <= 0:
                self._end_episode(Outcome.FELL)
            return

        # Autopilot runs regardless of focus; it sends no real input.
        if not self.options.autopilot and not self._handle_focus():
            return
        forward, strafe, turn = self._controls(dt)
        self.state = step(self.episode.layout, self.state, forward, strafe, turn, dt)
        self._sync_view()
        outcome = self.episode.update(self.state, dt)
        self.clock_text.text = f"{math.ceil(self.episode.seconds_left)} s"
        if outcome is Outcome.FELL:
            self.fall_left = FALL_SECONDS
        elif outcome is not None:
            self._end_episode(outcome)

    def _handle_focus(self) -> bool:
        """Pause (and give the mouse back) while the window isn't focused."""
        focused = self._focused()
        if focused != self.had_focus:
            self._set_mouse_captured(focused)
            self.had_focus = focused
            logger.info("window %s", "focused: playing" if focused else "not focused: paused")
            self.overlay.enabled = self.overlay_text.enabled = not focused
            if not focused:
                self.overlay.color = self._color((0, 0, 0), 170)
                # Once it's in front the mouse turns the character, as in any shooter: a
                # person watching PlayerTwo play must leave the mouse alone (Alt+Tab out).
                self.overlay_text.text = (
                    "PAUSED\nclick to play\n\n"
                    "the mouse turns the player:\nhands off while the AI plays"
                )
                self.overlay_text.scale = 3
            return False  # skip this frame's mouse delta: the pointer was just centred
        return focused

    def _set_mouse_captured(self, captured: bool) -> None:
        from panda3d.core import WindowProperties

        props = WindowProperties()
        props.setCursorHidden(captured)
        self.app.win.requestProperties(props)
        assert self.mouse_look is not None  # created by _focused
        if captured:
            self.mouse_look.capture()
        else:
            self.mouse_look.release()

    def _controls(self, dt: float) -> tuple[float, float, float]:
        assert self.state is not None
        if self.autopilot is not None:
            command = self.autopilot.command(self.state, dt)
            return command.forward, 0.0, command.turn_degrees
        held = self.u.held_keys
        forward = float(held["w"]) - float(held["s"])
        strafe = float(held["d"]) - float(held["a"])
        assert self.mouse_look is not None
        dx = self.mouse_look.take_dx()
        if dx:
            logger.debug("mouse %+d px: turned %+.1f degrees", dx, dx * TURN_DEGREES_PER_PIXEL)
        return forward, strafe, dx * TURN_DEGREES_PER_PIXEL

    def _sync_view(self) -> None:
        u = self.u
        assert self.state is not None
        s = self.state
        y = -self.fall_depth
        self.player_body.position = (s.x, y, s.z)
        self.player_body.rotation_y = s.heading
        rad = math.radians(s.heading)
        fx, fz = math.sin(rad), math.cos(rad)
        u.camera.position = (
            s.x - fx * CAMERA_DISTANCE,
            CAMERA_HEIGHT,
            s.z - fz * CAMERA_DISTANCE,
        )
        # Set the angles outright. Ursina's look_at rotates relative to the current
        # orientation, so 30-degree turns piled up roll until the view was upside down.
        u.camera.rotation = (CAMERA_PITCH, s.heading, 0)

    def _input(self, key: str) -> None:
        if key == "escape":
            self._quit()

    def _quit(self) -> None:
        if self.mouse_look is not None:
            self.mouse_look.release()
        self.u.application.quit()

    def _save_screenshot(self) -> None:
        from panda3d.core import Filename

        directory = self.options.screenshot_dir
        assert directory is not None and self.episode is not None
        directory.mkdir(parents=True, exist_ok=True)
        layout = self.episode.layout
        path = directory / f"level{layout.level}-seed{layout.seed}.png"
        self.app.win.saveScreenshot(Filename.fromOsSpecific(str(path)))
        print(f"screenshot {path}", flush=True)
