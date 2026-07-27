"""
subprocess_wrapper.py: Wrapper for subprocess module to better handle errors and output
"""
import shlex
import logging
import subprocess


def run(*args, **kwargs) -> subprocess.CompletedProcess:
    """
    Basic subprocess.run wrapper.
    """
    return subprocess.run(*args, **kwargs)


def run_as_root(*args, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command with root privileges using macOS native GUI authentication.

    Elevation is performed through AppleScript's
    'do shell script ... with administrator privileges'. This is the only
    elevation path that works reliably from a GUI / no-TTY context: plain
    `sudo` cannot prompt for a password without a controlling terminal, and
    `sudo -n` fails when no timestamp is cached. Privileged `diskutil mount`
    works through this path because diskutil delegates the actual mount to
    diskarbitrationd (which mounts on behalf of the console user).

    IMPORTANT: Do NOT use this path to write directly onto an FSKit-backed
    volume (msdos / EFI System Partition on macOS 15 Sequoia and newer). The
    elevated command runs in a different security session than the one that
    owns the FSKit mount, so FSKit rejects the write with EPERM
    ("Operation not permitted") even though the caller is root. Such a volume
    is owned by and writable to the current user, so callers must use run()
    for those file operations instead (see install.py).
    """
    if not args or not args[0]:
        raise ValueError("No command provided")

    # Normalise the command (which may contain pathlib.Path entries) into a
    # single POSIX-shell-safe string for `do shell script`.
    command = [str(arg) for arg in args[0]]
    shell_command = shlex.join(command)

    # Escape the shell string for embedding inside an AppleScript
    # double-quoted string literal (backslash first, then double-quote).
    applescript_literal = shell_command.replace("\\", "\\\\").replace('"', '\\"')
    script = f'do shell script "{applescript_literal}" with administrator privileges'

    return subprocess.run(["osascript", "-e", script], **kwargs)


def verify(process_result: subprocess.CompletedProcess) -> None:
    """
    Verify process result and raise exception if failed.
    """
    if process_result.returncode == 0:
        return
    log(process_result)
    raise Exception(f"Process failed with exit code {process_result.returncode}")


def run_and_verify(*args, **kwargs) -> None:
    """
    Run subprocess and verify result.
    """
    verify(run(*args, **kwargs))


def run_as_root_and_verify(*args, **kwargs) -> None:
    """
    Run subprocess as root and verify result.
    """
    verify(run_as_root(*args, **kwargs))


def log(process: subprocess.CompletedProcess) -> None:
    """
    Display subprocess error output in formatted string.
    """
    for line in generate_log(process).split("\n"):
        logging.error(line)


def generate_log(process: subprocess.CompletedProcess) -> str:
    """
    Display subprocess error output in formatted string.
    """
    output = "Subprocess failed.\n"
    output += f" Command: {process.args}\n"
    output += f" Return Code: {process.returncode}\n"
    output += "    Standard Output:\n"
    output += __format_stream(process.stdout)

    output += "    Standard Error:\n"
    output += __format_stream(process.stderr)

    return output


def __format_stream(stream) -> str:
    """
    Decode and format a subprocess stream (bytes or str) for logging.
    """
    if stream is None:
        return "        None\n"
    if isinstance(stream, (bytes, bytearray)):
        stream = stream.decode("utf-8", errors="ignore")
    return __format_output(stream)


def __format_output(output: str) -> str:
    """
    Format output.
    """
    if not output:
        return " None\n"
    _result = "\n".join([f"        {line}" for line in output.split("\n") if line.strip()])
    if not _result.endswith("\n"):
        _result += "\n"
    return _result
