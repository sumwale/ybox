"""Unit tests for `ybox/cmd.py`"""

import argparse
import os
import shlex
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from ybox import __version__ as product_version
from ybox.cmd import (YboxLabel, build_shell_command, check_active_ybox,
                      check_ybox_exists, get_ybox_state, page_command,
                      page_output, parse_opt_deps_args, parser_version_check,
                      run_command)
from ybox.env import get_docker_command
from ybox.print import fgcolor


def proc_run(cmd: list[str], capture_output: bool = False,
             **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    """shortcut to invoke `subprocess.run`"""
    return cast(subprocess.CompletedProcess[bytes],
                subprocess.run(cmd, capture_output=capture_output, check=False, **kwargs))


_TEST_IMAGE = "alpine"
_TEST_DISTRO = "alpine"


def _stop_container(docker_cmd: str, name: str, check_removed: bool = False) -> None:
    """stop given container and wait for it to disappear from container running list"""
    proc_run([docker_cmd, "container", "stop", name])
    end = datetime.now() + timedelta(seconds=30)
    docker_args = [docker_cmd, "container", "ls", "-q", "-f", f"name={name}"]
    if check_removed:
        docker_args.append("-a")
    while datetime.now() < end:
        output = proc_run(docker_args, capture_output=True)
        if not output.stdout.decode("utf-8").strip():
            return
        time.sleep(0.5)
    raise ChildProcessError(f"Failed to stop container {name}")


def test_check_ybox_state(capsys: pytest.CaptureFixture[str]):
    """
    Check various cases for `check_ybox_state` and related functions (also `build_shell_command`)
    """
    docker_cmd = get_docker_command()
    cnt_name = f"ybox-test-cmd-{uuid4()}"
    # command to run in containers which allows them to stop immediately
    sh_cmd = 'tail -s10 -f /dev/null & childPID=$!; trap "kill -TERM $childPID" 1 2 3 15; wait'
    try:
        # check failure to match ybox without label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, _TEST_IMAGE,
                  "/bin/sh", "-c", sh_cmd])
        assert not get_ybox_state(docker_cmd, cnt_name, expected_states=["running"],
                                  exit_on_error=False)
        assert not check_active_ybox(docker_cmd, cnt_name)
        assert not check_active_ybox(docker_cmd, cnt_name, exit_on_error=False)
        assert not get_ybox_state(docker_cmd, cnt_name, expected_states=())
        assert not check_ybox_exists(docker_cmd, cnt_name)
        assert not check_ybox_exists(docker_cmd, cnt_name, exit_on_error=False)
        pytest.raises(SystemExit, get_ybox_state, docker_cmd, cnt_name,
                      expected_states=["running"], exit_on_error=True)
        pytest.raises(SystemExit, check_active_ybox, docker_cmd, cnt_name, exit_on_error=True)
        pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)

        # check `build_shell_command`
        run_cmd = "run-user-bash-cmd"
        run_cmd_path = f"/usr/local/bin/{run_cmd}"
        src_resources_dir = f"{os.path.dirname(__file__)}/../../src/ybox/conf/resources"
        assert proc_run([docker_cmd, "cp", f"{src_resources_dir}/{run_cmd}",
                         f"{cnt_name}:{run_cmd_path}"]).returncode == 0
        assert proc_run([docker_cmd, "exec", cnt_name, "chmod", "755",
                         run_cmd_path]).returncode == 0
        assert proc_run([docker_cmd, "exec", cnt_name, "apk", "add", "bash"]).returncode == 0
        for pty in (None, False, True):
            if pty is None:
                bash_cmd = build_shell_command(docker_cmd, cnt_name, "uname -s")
            else:
                bash_cmd = build_shell_command(docker_cmd, cnt_name, "uname -s", enable_pty=pty)
            assert run_cmd_path in bash_cmd and "uname -s" in bash_cmd
            output = proc_run(bash_cmd, capture_output=True)
            out = output.stdout.decode("utf-8").strip()
            if pty is False:
                assert "-it" not in bash_cmd
                assert out == "Linux"
            else:
                assert "-it" in bash_cmd
                # fails with docker but succeeds with podman, so check both cases
                if "not a tty" in output.stderr.decode("utf-8").lower():
                    assert out == ""
                else:
                    assert out.endswith("Linux")

        _stop_container(docker_cmd, cnt_name, check_removed=True)
        # check success with primary label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_PRIMARY.value, "--label",
                  f"{YboxLabel.CONTAINER_DISTRIBUTION.value}={_TEST_DISTRO}", _TEST_IMAGE,
                  "/bin/sh", "-c", sh_cmd])
        assert get_ybox_state(docker_cmd, cnt_name, expected_states=("running",),
                              exit_on_error=False) == ("running", _TEST_DISTRO)
        assert check_active_ybox(docker_cmd, cnt_name)
        assert check_ybox_exists(docker_cmd, cnt_name)
        _stop_container(docker_cmd, cnt_name, check_removed=True)

        # check success with primary label and stopped state
        proc_run([docker_cmd, "run", "-itd", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_PRIMARY.value, "--label",
                  f"{YboxLabel.CONTAINER_DISTRIBUTION.value}={_TEST_DISTRO}", _TEST_IMAGE,
                  "/bin/sh", "-c", sh_cmd])
        _stop_container(docker_cmd, cnt_name)
        assert not get_ybox_state(docker_cmd, cnt_name, expected_states=["running"])
        assert not check_active_ybox(docker_cmd, cnt_name)
        pytest.raises(SystemExit, check_active_ybox, docker_cmd, cnt_name, exit_on_error=True)
        assert get_ybox_state(docker_cmd, cnt_name, expected_states=["stopped", "exited"],
                              exit_on_error=False) == ("exited", _TEST_DISTRO)
        assert get_ybox_state(docker_cmd, cnt_name, expected_states=("stopped", "exited"),
                              exit_on_error=False) == ("exited", _TEST_DISTRO)
        assert get_ybox_state(docker_cmd, cnt_name, expected_states=[]) == ("exited", _TEST_DISTRO)
        assert check_ybox_exists(docker_cmd, cnt_name, exit_on_error=False)
        proc_run([docker_cmd, "container", "rm", cnt_name])
        assert not get_ybox_state(docker_cmd, cnt_name, expected_states=[])
        assert not check_ybox_exists(docker_cmd, cnt_name)

        # check error and the messages on stdout
        pytest.raises(SystemExit, get_ybox_state, docker_cmd, cnt_name, expected_states=[],
                      exit_on_error=True)
        captured = capsys.readouterr()
        assert f"No ybox container '{cnt_name}' found" in captured.err
        pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)
        captured = capsys.readouterr()
        assert f"No ybox container '{cnt_name}' found" in captured.err
        pytest.raises(SystemExit, get_ybox_state, docker_cmd, cnt_name, expected_states=[],
                      exit_on_error=True, state_msg=" running or stopped")
        captured = capsys.readouterr()
        assert f"No running or stopped ybox container '{cnt_name}' found" in captured.err

        # check failure with non-primary label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_BASE.value, "--label",
                  f"{YboxLabel.CONTAINER_DISTRIBUTION.value}={_TEST_DISTRO}", _TEST_IMAGE,
                  "/bin/sh", "-c", sh_cmd])
        assert not check_active_ybox(docker_cmd, cnt_name)
        assert not check_ybox_exists(docker_cmd, cnt_name)
        pytest.raises(SystemExit, get_ybox_state, docker_cmd, cnt_name, expected_states=[],
                      exit_on_error=True)
        pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)
    finally:
        proc_run([docker_cmd, "container", "stop", cnt_name])
        proc_run([docker_cmd, "container", "rm", cnt_name], stderr=subprocess.DEVNULL)


def test_run_command(capsys: pytest.CaptureFixture[str]):
    """check various cases for `run_command` function"""

    # check string and list arguments for run_command
    expected = [f for f in os.listdir("/") if not f.startswith('.')]
    expected.sort()
    output = run_command("/bin/ls /", capture_output=True)
    assert isinstance(output, str)
    output_list = output.splitlines()
    output_list.sort()
    assert output_list == expected
    output = run_command(["/bin/ls", "/"], capture_output=True)
    assert isinstance(output, str)
    output_list = output.splitlines()
    output_list.sort()
    assert output_list == expected

    # check failure on non-existent command
    assert run_command("/non-existent", exit_on_error=False) == 2
    captured = capsys.readouterr()
    assert "FAILURE invoking '/non-existent'" in captured.err
    pytest.raises(FileNotFoundError, run_command, "/non-existent", exit_on_error=True)

    # check capture_output=True and default/False
    pwd = os.getcwd()
    assert str(run_command("/bin/pwd", capture_output=True)).splitlines() == [pwd]
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"]) == 0
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"], capture_output=False) == 0
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"], capture_output=True) == ""
    assert str(run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ] && pwd"],
                           capture_output=True)).rstrip() == pwd
    pytest.raises(SystemExit, run_command, ["/bin/sh", "-c", "[ \"`pwd`\" = \"\" ]"])
    captured = capsys.readouterr()
    assert "FAILURE in '[\'/bin/sh\', \'-c\', " in captured.err
    # check capture_output=True with output on stderr
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ] && pwd >&2"],
                       capture_output=True) == ""
    captured = capsys.readouterr()
    assert f"{fgcolor.purple}{pwd}\n{fgcolor.reset}" == captured.err.rstrip()
    assert run_command(["/bin/sh", "-c", "pwd >&2 && pwd && [ \"`pwd`\" = \"\" ]"],
                       capture_output=True, exit_on_error=False, error_msg="SKIP") == 1
    captured = capsys.readouterr()
    assert f"{fgcolor.purple}{pwd}\n{fgcolor.reset}" == captured.err.rstrip()
    assert f"{fgcolor.orange}{pwd}\n{fgcolor.reset}" == captured.out.rstrip()

    # check exit_on_error=False
    assert run_command(["/bin/sh", "-c", "[ \"`pwd`\" = \"\" ]"], exit_on_error=False) != 0
    # check default error_msg
    captured = capsys.readouterr()
    assert "FAILURE in '[\'/bin/sh\', \'-c\', " in captured.err

    # check with specified error_msg
    non_existent = f"/{uuid4()}"
    pytest.raises(SystemExit, run_command, f"/bin/ls {non_existent}", capture_output=True,
                  error_msg="running /bin/ls")
    captured = capsys.readouterr()
    assert "No such file or directory" in captured.err
    assert "FAILURE in running /bin/ls" in captured.err

    # check error_msg=SKIP
    pytest.raises(SystemExit, run_command, f"/bin/ls {non_existent}", capture_output=True,
                  error_msg="SKIP")
    captured = capsys.readouterr()
    assert "No such file or directory" in captured.err
    assert "FAILURE in" not in captured.err


def test_parse_args_with_version_check(capsys: pytest.CaptureFixture[str]):
    """check the `parse_args_with_version_check` function"""
    parser = argparse.ArgumentParser(description="Test for --version")
    parser_version_check(parser, [])
    args = parser.parse_args([])
    assert not args.version
    # check success
    parser = argparse.ArgumentParser(description="Test for --version")
    with pytest.raises(SystemExit) as exc_info:
        parser_version_check(parser, ["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == product_version

    # check success with optional arguments
    parser = argparse.ArgumentParser(description="Test for --version with optional args")
    parser.add_argument("-f", "--format", type=str)
    parser_version_check(parser, ["--format", "FMT"])
    args = parser.parse_args(["--format", "FMT"])
    assert not args.version
    assert args.format == "FMT"
    args = parser.parse_args(["--format", "FMT2", "--version"])
    assert args.version
    assert args.format == "FMT2"
    parser = argparse.ArgumentParser(description="Test for --version with optional args")
    parser.add_argument("-f", "--format", type=str)
    with pytest.raises(SystemExit) as exc_info:
        parser_version_check(parser, ["--format", "FMT", "--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == product_version

    # check success with required arguments even when the required arguments are absent
    parser = argparse.ArgumentParser(description="Test for --version with required args")
    parser.add_argument("-f", "--format", type=str)
    parser.add_argument("operation", type=str)
    parser.add_argument("package", type=str)
    with pytest.raises(SystemExit) as exc_info:
        parser_version_check(parser, ["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == product_version


def test_parse_opt_deps_args():
    """check the `parse_opt_deps` function"""
    pytest.raises(SystemExit, parse_opt_deps_args, [])
    args = parse_opt_deps_args(["firefox"])
    assert args.separator == "::::"
    assert args.prefix == ""
    assert args.header == ""
    assert args.level == 2
    args = parse_opt_deps_args(["-s", ";", "-pPKG:", "-H", "START", "-l1", "firefox"])
    assert args.separator == ";"
    assert args.prefix == "PKG:"
    assert args.header == "START"
    assert args.level == 1


def test_page_output(capfd: pytest.CaptureFixture[str]):
    """check various cases for `page_output` function"""
    # first check normal output with no paging
    out = (b"test", b"output", b"with or without", b"pager\n")
    str_out = "".join((w.decode("utf-8") for w in out))
    assert page_output(out, pager="") == 0
    captured = capfd.readouterr()
    assert captured.out == str_out
    # test failure for non-existent pager
    assert page_output(out, "/non-existent") == 2
    captured = capfd.readouterr()
    assert "FAILURE invoking pager '/non-existent'" in captured.err
    # test pager invocation
    # sed does not page, but it tests output being piped and arguments being split with spaces
    pager = "/usr/bin/sed 's, or ,/,g'"
    assert page_output(out, pager) == 0
    captured = capfd.readouterr()
    assert captured.out == str_out.replace(" or ", "/")
    # mock for broken pipe with pager
    with patch("ybox.cmd.subprocess.Popen", side_effect=BrokenPipeError):
        assert page_output(out, "less") == 0
    # mock for keyboard interrupt
    with patch("ybox.cmd.subprocess.Popen", side_effect=KeyboardInterrupt):
        assert page_output(out, "less") == 130
        captured = capfd.readouterr()
        assert "Interrupt" in captured.out
    # check for non-zero exit of pager
    pager = "/bin/sh -c '/usr/bin/cat && exit 12'"
    assert page_output(out, pager) == 12
    captured = capfd.readouterr()
    assert captured.out == str_out


def test_page_command(capfd: pytest.CaptureFixture[str]):
    """check various cases for `page_command` function"""
    # first check normal output with or without pager
    check_str = "test page_command"
    cmd = f"/bin/echo -n '{check_str}'"
    pager = "/usr/bin/less -RL"
    assert page_command(cmd, "") == 0
    captured = capfd.readouterr()
    assert captured.out == check_str
    assert page_command(cmd, pager) == 0
    captured = capfd.readouterr()
    assert captured.out == check_str
    assert page_command(shlex.split(cmd), pager) == 0
    captured = capfd.readouterr()
    assert captured.out == check_str
    # check command and pager failure for non-existent programs
    assert page_command("/non-existent", pager) == 2
    captured = capfd.readouterr()
    assert "FAILURE invoking '/non-existent'" in captured.err
    assert page_command(cmd, "/non-existent") == 2
    captured = capfd.readouterr()
    assert "FAILURE invoking pager '/non-existent'" in captured.err
    # check empty output from command
    assert page_command("/bin/echo -n ''", pager) == 0
    # check output transform
    assert page_command(cmd, pager, transform=lambda s: s.upper()) == 0
    captured = capfd.readouterr()
    assert captured.out == check_str.upper()
    # check header in output
    assert page_command(cmd, pager, transform=lambda s: s.upper(), header="Header:\n") == 0
    captured = capfd.readouterr()
    assert captured.out == f"Header:\n{check_str.upper()}"


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
