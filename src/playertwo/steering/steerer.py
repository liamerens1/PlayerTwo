"""Turns "where is the target?" into one of the profile's actions. No model, no input."""

from playertwo.actions import Decision, Sighting, SteerTarget


class Steerer:
    """Steers towards a target the model has located.

    - not visible: turn towards the side it was last seen on (or `target.search` if it
      never has been), so a lost target is found again by the shortest turn;
    - left of the centre band: turn left; right of it: turn right. With nudges, a target
      near the centre (within `nudge_zone`) gets a small turn instead, and so does one that
      just swung past the centre after a turn the other way (overshoot), so steering
      settles instead of swinging from side to side;
    - inside the band: walk forward;
    - stuck (walking stopped changing the screen) and the profile has sidesteps: detour
      `detour_steps` sidesteps towards the target's side (the same way as last time if
      it's dead ahead), then steer again. Strafing keeps the target in view.

    A sighting of None means the model couldn't answer; that's a `wait`, not "not
    visible", so a broken reply never sends the character spinning.

    Remembers only which side the target was last seen on. Used by the brain thread only.
    """

    def __init__(self, target: SteerTarget) -> None:
        self._target = target
        self._last_side: str = target.search
        self._last_turn: str | None = None
        """Side of the last turn or nudge, to spot an overshoot."""
        self._detour_side: str | None = None
        self._detour_left = 0
        """Sidesteps still to take in the current detour."""

    @property
    def can_detour(self) -> bool:
        return self._target.sidestep_left is not None

    def needs_look(self, stuck: bool) -> bool:
        """False while detouring (or starting one): the next move doesn't depend on the
        screen, so the model needn't be asked."""
        return not (self._detour_left > 0 or (stuck and self.can_detour))

    def decide(self, sighting: Sighting | None, stuck: bool = False) -> Decision:
        target = self._target
        if self._detour_left > 0 or (stuck and self.can_detour):
            return self._detour(starting=self._detour_left == 0)
        if sighting is None:
            return Decision.wait("couldn't locate the target")
        if not sighting.visible or sighting.x is None:
            turn = target.turn_left if self._last_side == "left" else target.turn_right
            self._last_turn = None
            return Decision(action=turn, reason=f"searching {self._last_side}")
        x = sighting.x
        offset = x - 0.5
        if abs(offset) <= target.centre_width / 2:
            # Centred: remember which half it was in, for if it drifts out of view.
            self._last_side = "left" if offset < 0 else "right"
            self._last_turn = None
            return Decision(action=target.forward, reason=f"target ahead (x={x:.2f})")
        side = "left" if offset < 0 else "right"
        overshoot = self._last_turn is not None and self._last_turn != side
        self._last_side = side
        self._last_turn = side
        nudge = target.nudge_left if side == "left" else target.nudge_right
        if nudge is not None and (abs(offset) <= target.nudge_zone or overshoot):
            why = "overshot, " if overshoot else ""
            return Decision(action=nudge, reason=f"{why}target slightly {side} (x={x:.2f})")
        turn = target.turn_left if side == "left" else target.turn_right
        return Decision(action=turn, reason=f"target {side} (x={x:.2f})")

    def _detour(self, starting: bool) -> Decision:
        target = self._target
        assert target.sidestep_left is not None and target.sidestep_right is not None
        if starting:
            # Towards the target's side; dead ahead, keep the side of the last detour.
            if self._last_turn is not None:
                self._detour_side = self._last_turn
            elif self._detour_side is None:
                self._detour_side = self._last_side
            self._detour_left = target.detour_steps
            self._last_turn = None
        self._detour_left -= 1
        side = self._detour_side or "right"
        action = target.sidestep_left if side == "left" else target.sidestep_right
        return Decision(action=action, reason=f"blocked: detour {side} ({self._detour_left} more)")
