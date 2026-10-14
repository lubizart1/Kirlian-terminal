import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time

import pytest
from terminal_protocol import unwrap_tmux


@pytest.mark.parametrize("identity", ["libghostty", "ghostty 1.3.1", ""])
@pytest.mark.parametrize("multiplexed", [False, True])
def test_automatic_backend_uses_live_identity_and_keeps_native_override(identity, multiplexed):
    """Exercise startup ordering with inherited Ghostty environment variables."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 800, 480))
    before = termios.tcgetattr(slave)
    env = dict(os.environ, TERM="xterm-256color", TERM_PROGRAM="ghostty")
    env.pop("TMUX", None)
    env.pop("STY", None)
    if multiplexed:
        env["TMUX"] = "/tmp/kirlian-test,1,0"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import json
from kirlian_terminal.graphics import TerminalImage, image_widget
from kirlian_terminal.cover import CoverImage
from kirlian_terminal.terminal_support import query_terminal_version
print('RESULT ' + json.dumps({
    'renderer': TerminalImage.__name__,
    'override': image_widget(force=True).__name__,
    'cover': CoverImage().mode,
    'identity': query_terminal_version(),
    'cached_identity': query_terminal_version(),
}))
""",
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
    )
    output = bytearray()
    answered = set()
    version_queries = 0
    commands = re.compile(rb"\x1b_G([^\x1b]*)\x1b\\|\x1b\[c|\x1b\[>q")
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.03)[0]:
                output.extend(os.read(master, 65536))
            # Emulate only tmux's envelope, not its layout or image lifecycle.
            stream = output
            if multiplexed:
                stream = unwrap_tmux(output)
            for match in commands.finditer(stream):
                if match.start() in answered:
                    continue
                answered.add(match.start())
                if match[0] == b"\x1b[c":
                    os.write(master, b"\x1b[?1;2c")
                elif match[0] == b"\x1b[>q":
                    version_queries += 1
                    if identity:
                        os.write(master, b"\x1bP>|" + identity.encode() + b"\x1b\\")
                else:
                    image_id = re.search(rb"(?:^|,)i=(\d+)", match[1])[1]
                    os.write(master, b"\x1b_Gi=" + image_id + b";OK\x1b\\")
            if process.poll() is not None:
                while select.select([master], [], [], 0)[0]:
                    output.extend(os.read(master, 65536))
                break
        assert process.poll() == 0, output
        after = termios.tcgetattr(slave)
        # macOS may mark unread input for retyping when canonical mode returns.
        # PENDIN is kernel bookkeeping, not a changed echo/canonical setting.
        after[3] &= ~getattr(termios, "PENDIN", 0)
        before[3] &= ~getattr(termios, "PENDIN", 0)
        assert after == before
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        os.close(master)
        os.close(slave)
    result = json.loads(re.search(rb"RESULT (\{[^\r\n]+\})", output)[1])
    embedded = identity == "libghostty"
    assert result["renderer"] == ("HalfcellImage" if embedded else "KittyImage")
    assert result["cover"] == ("blocks" if embedded else "native")
    assert result["override"] == "KittyImage"
    assert result["identity"] == result["cached_identity"] == (identity or "no reply")
    assert version_queries == 1
