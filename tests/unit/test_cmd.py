"""Unit tests for `ybox/cmd.py`"""

import argparse
import io
import os
import re
import subprocess
import time
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest

from ybox.cmd import (YboxLabel, check_active_ybox, check_ybox_exists,
                      check_ybox_state, get_docker_command, run_command)


def proc_run(cmd: list[str], capture_output: bool = False,
             **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    """shortcut to invoke `subprocess.run`"""
    return cast(subprocess.CompletedProcess[bytes],
                subprocess.run(cmd, capture_output=capture_output, check=False, **kwargs))


_TEST_IMAGE = "busybox"


def _get_docker_cmd() -> tuple[str, argparse.ArgumentParser]:
    """build `argparse` and obtain docker/podman path using `get_docker_command`"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--docker-path")
    args = parser.parse_args([])
    docker_cmd = get_docker_command(args, "-d")
    return docker_cmd, parser


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


def test_get_docker_command():
    """check `get_docker_command` result"""
    docker_cmd, parser = _get_docker_cmd()
    assert docker_cmd is not None
    assert re.match(r"/usr/bin/(docker|podman)", docker_cmd)
    assert os.access(docker_cmd, os.X_OK)
    # try with explicit -d option
    args = parser.parse_args(["-d", "/bin/true"])
    docker_cmd = get_docker_command(args, "-d")
    assert docker_cmd == "/bin/true"


def test_check_ybox_state():
    """check various cases for `check_ybox_state` and related functions"""
    docker_cmd, _ = _get_docker_cmd()
    cnt_name = f"ybox-test-cmd-{uuid4()}"
    # command to run in containers which allows them to stop immediately
    sh_cmd = 'tail -s10 -f /dev/null & childPID=$!; trap "kill -TERM $childPID" 1 2 3 15; wait'
    try:
        # check failure to match ybox without label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, _TEST_IMAGE,
                  "/bin/sh", "-c", sh_cmd])
        assert not check_ybox_state(docker_cmd, cnt_name, expected_states=["running"],
                                    exit_on_error=False)
        assert not check_active_ybox(docker_cmd, cnt_name)
        assert not check_active_ybox(docker_cmd, cnt_name, exit_on_error=False)
        assert not check_ybox_state(docker_cmd, cnt_name, expected_states=[])
        assert not check_ybox_exists(docker_cmd, cnt_name)
        assert not check_ybox_exists(docker_cmd, cnt_name, exit_on_error=False)
        pytest.raises(SystemExit, check_ybox_state, docker_cmd, cnt_name,
                      expected_states=["running"], exit_on_error=True)
        pytest.raises(SystemExit, check_active_ybox, docker_cmd, cnt_name, exit_on_error=True)
        pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)
        _stop_container(docker_cmd, cnt_name, check_removed=True)
        # check success with primary label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_PRIMARY.value, _TEST_IMAGE, "/bin/sh", "-c",
                  sh_cmd])
        assert check_ybox_state(docker_cmd, cnt_name, expected_states=["running"],
                                exit_on_error=False)
        assert check_active_ybox(docker_cmd, cnt_name)
        assert check_ybox_exists(docker_cmd, cnt_name)
        _stop_container(docker_cmd, cnt_name, check_removed=True)
        # check success with primary label and stopped state
        proc_run([docker_cmd, "run", "-itd", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_PRIMARY.value, _TEST_IMAGE, "/bin/sh", "-c",
                  sh_cmd])
        _stop_container(docker_cmd, cnt_name)
        assert not check_ybox_state(docker_cmd, cnt_name, expected_states=["running"])
        assert not check_active_ybox(docker_cmd, cnt_name)
        pytest.raises(SystemExit, check_active_ybox, docker_cmd, cnt_name, exit_on_error=True)
        assert check_ybox_state(docker_cmd, cnt_name, expected_states=["stopped", "exited"],
                                exit_on_error=False)
        assert check_ybox_state(docker_cmd, cnt_name, expected_states=[])
        assert check_ybox_exists(docker_cmd, cnt_name, exit_on_error=False)
        proc_run([docker_cmd, "container", "rm", cnt_name])
        assert not check_ybox_state(docker_cmd, cnt_name, expected_states=[])
        assert not check_ybox_exists(docker_cmd, cnt_name)
        # check error and the messages on stdout
        str_io = io.StringIO()
        with redirect_stdout(str_io):
            pytest.raises(SystemExit, check_ybox_state, docker_cmd, cnt_name, expected_states=[],
                          exit_on_error=True)
        assert f"No ybox container named '{cnt_name}' found" in str_io.getvalue()
        str_io.truncate(0)
        with redirect_stdout(str_io):
            pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)
        assert f"No ybox container named '{cnt_name}' found" in str_io.getvalue()
        str_io.truncate(0)
        with redirect_stdout(str_io):
            pytest.raises(SystemExit, check_ybox_state, docker_cmd, cnt_name, expected_states=[],
                          exit_on_error=True, cnt_state_msg=" running or stopped")
        assert f"No running or stopped ybox container named '{cnt_name}' found" in \
            str_io.getvalue()

        # check failure with non-primary label
        proc_run([docker_cmd, "run", "-itd", "--rm", "--name", cnt_name, "--label",
                  YboxLabel.CONTAINER_BASE.value, _TEST_IMAGE, "/bin/sh", "-c", sh_cmd])
        assert not check_active_ybox(docker_cmd, cnt_name)
        assert not check_ybox_exists(docker_cmd, cnt_name)
        pytest.raises(SystemExit, check_ybox_state, docker_cmd, cnt_name, expected_states=[],
                      exit_on_error=True)
        pytest.raises(SystemExit, check_ybox_exists, docker_cmd, cnt_name, exit_on_error=True)
    finally:
        proc_run([docker_cmd, "container", "stop", cnt_name])
        proc_run([docker_cmd, "container", "rm", cnt_name], stderr=subprocess.DEVNULL)


def test_run_command():
    """check various cases for `run_command` function"""
    # check string and list arguments for run_command
    expected = [f for f in os.listdir("/") if not f.startswith('.')]
    expected.sort()
    output = run_command("/bin/ls /", capture_output=True)
    assert isinstance(output, str)
    assert str(output).splitlines() == expected
    output = run_command(["/bin/ls", "/"], capture_output=True)
    assert isinstance(output, str)
    assert str(output).splitlines() == expected

    # check capture_output=True and default/False
    pwd = os.getcwd()
    assert str(run_command("/bin/pwd", capture_output=True)).splitlines() == [pwd]
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"]) == 0
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"], capture_output=False) == 0
    assert run_command(["/bin/sh", "-c", f"[ \"`pwd`\" = \"{pwd}\" ]"], capture_output=True) == ""
    str_io = io.StringIO()
    with redirect_stdout(str_io):
        pytest.raises(SystemExit, run_command, ["/bin/sh", "-c", "[ \"`pwd`\" = \"\" ]"])
    assert "FAILURE in '/bin/sh -c" in str_io.getvalue()

    # check exit_on_error=False
    str_io.truncate(0)
    with redirect_stdout(str_io):
        assert run_command(["/bin/sh", "-c", "[ \"`pwd`\" = \"\" ]"], exit_on_error=False) != 0
    # check default error_msg
    assert "FAILURE in '/bin/sh -c" in str_io.getvalue()

    # check with specified error_msg
    str_io.truncate(0)
    non_existent = f"/{uuid4()}"
    with redirect_stdout(str_io):
        pytest.raises(SystemExit, run_command, f"/bin/ls {non_existent}", capture_output=True,
                      error_msg="running /bin/ls")
    out = str_io.getvalue()
    assert "No such file or directory" in out
    assert "FAILURE in running /bin/ls" in out

    # check error_msg=SKIP
    str_io.truncate(0)
    with redirect_stdout(str_io):
        pytest.raises(SystemExit, run_command, f"/bin/ls {non_existent}", capture_output=True,
                      error_msg="SKIP")
    out = str_io.getvalue()
    assert "No such file or directory" in out
    assert "FAILURE in" not in out


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
