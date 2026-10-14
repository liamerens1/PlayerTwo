"""PlayerTwo Testbed: a tiny third-person game made for testing PlayerTwo.

Separate from `playertwo` on purpose: neither imports the other. They meet only through
the screen and the keyboard and mouse, like PlayerTwo and any real game. Run it with
`python -m testbed --level N`; it needs the `testbed` extra (`pip install -e ".[testbed]"`).

Everything except `testbed.game` is pure logic and imports without Ursina.
"""
