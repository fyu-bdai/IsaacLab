# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from utils.statefile import Statefile


class IsaacLabContainerInterface:
    """
    Interface for managing Isaac Lab containers.
    """

    def __init__(
        self,
        dir: Path,
        target: str = "base",
        statefile: None | Statefile = None,
        yamls: list[str] | None = None,
        envs: list[str] | None = None,
    ):
        """
        Initialize the IsaacLabContainerInterface with the given parameters.

        Args:
            dir: The directory for Docker operations.
            target: The target name for the container. Defaults to "base".
            statefile: An instance of the Statefile class to manage state variables. If not provided, initializes a Statefile(path=self.dir/.container.cfg).
            yamls: A list of yamls to merge with the produced yaml. They will be extended in the order they are provided.
            envs: A list of envs to be merged with with the .env at the project root if it exists. They will be extended in the order they are provided.
        """
        self.dir = dir
        self.yamls_dir = Path(self.dir / "yamls")
        if not self.yamls_dir.is_dir():
            raise FileNotFoundError(f"Required directory {self.yamls_dir} was not found.")
        if statefile is None:
            self.statefile = Statefile(path=self.dir / ".container.cfg")
        else:
            self.statefile = statefile
        print(f"[INFO] Using statefile {self.statefile.path}")
        self.target = target
        if self.target == "isaaclab":
            # Silently correct from isaaclab to base,
            # because isaaclab is a commonly passed arg
            # but not a real target
            self.target = "base"
        self.container_name = f"isaac-lab-{self.target}"
        self.image_name = f"isaac-lab-{self.target}:latest"
        self.environ = os.environ
        self.environ.update({"TARGET": self.target})
        self.resolve_compose_cfg(yamls, envs)
        self.load_dot_vars()

    def resolve_compose_cfg(
        self,
        yamls: list[str] | None = None,
        envs: list[str] | None = None,
    ):
        """
        Resolve the compose configuration by setting up YAML files and environment files for the Docker compose command.

        Args:
            yamls: A list of yamls to merge with the produced yaml. They will be extended in the order they are provided.
            envs: A list of envs to be merged with the .env at the project root if it exists. They will be extended in the order they are provided.
        """
        self.yamls = []
        # Search cfgs for the 'target.yaml'. However, if it does not exist
        # there let it be supplied as an abs path by --files args
        if self.search_compose_cfgs(f"{self.target}.yaml", required=False):
            self.yamls.append(f"{self.target}.yaml")

        self.env_files = []
        root_env = Path(self.dir / ".env")
        # If there is a .env file in self.dir, load its values into the environ
        if os.path.isfile(root_env):
            self.env_files.append(root_env)

        if yamls is not None:
            self.yamls += yamls

        if envs is not None:
            self.env_files += envs

    @property
    def dot_vars(self):
        self.load_dot_vars()
        return self._dot_vars

    def load_dot_vars(self):
        """
        Load environment variables from .env files into a dictionary.

        The environment variables are read in order and overwritten if there are name conflicts,
        mimicking the behavior of Docker compose.
        """
        self._dot_vars: dict[str, Any] = {}
        abs_env_files = [self.search_compose_cfgs(file) for file in self.env_files]
        for i in range(len(abs_env_files)):
            with open(self.dir / abs_env_files[i]) as f:
                self._dot_vars.update(dict(line.strip().split("=", 1) for line in f if "=" in line))

    def add_env_files(self) -> list[str]:
        """
        Put self.env_files into a state suitable for the docker compose CLI, with '--env-file' between
        every argument

        Returns:
            A list of strings, with '--env-file' first and then interpolated between the strings of
            self.env_files
        """
        abs_env_files = [self.search_compose_cfgs(file) for file in self.env_files]
        return [abs_env_files[int(i / 2)] if i % 2 == 1 else "--env-file" for i in range(len(abs_env_files) * 2)]

    def add_yamls(self) -> list[str]:
        """
        Put self.yamls into a state suitable for the docker compose CLI, with '--file' between
        every argument

        Returns:
            A list of strings, with '--file' first and then interpolated between the strings of
            self.yamls
        """
        abs_yaml_files = [self.search_compose_cfgs(file) for file in self.yamls]
        return [abs_yaml_files[int(i / 2)] if i % 2 == 1 else "--file" for i in range(len(abs_yaml_files) * 2)]

    def is_container_running(self) -> bool:
        """
        Check if the container is running.

        If the container is not running, return False.

        Returns:
            True if the container is running, False otherwise.
        """
        status = subprocess.run(
            [
                "docker",
                "container",
                "inspect",
                "-f",
                "{{.State.Status}}",
                self.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return status == "running"

    def does_image_exist(self) -> bool:
        """
        Check if the Docker image exists.

        If the image does not exist, return False.

        Returns:
            True if the image exists, False otherwise.
        """
        result = subprocess.run(
            ["docker", "image", "inspect", self.image_name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def up(self, cli_args: list[str] | None = None):
        """
        Build and start the Docker container using the Docker compose 'up' command.

        Args:
            cli_args: None by default, or a list with a string containing cli args for 'docker compose up'
        """
        print(f"[INFO] Bringing up the {self.container_name} compose network in the background...")
        if cli_args is None:
            cli_args = []
        else:
            cli_args = cli_args[0].split(" ")
        try:
            subprocess.run(
                ["docker", "compose"]
                + self.add_yamls()
                + self.add_env_files()
                + ["up", "--detach", "--remove-orphans"]
                + cli_args,
                check=True,
                cwd=self.dir,
                env=self.environ,
            )
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Unable to 'up' target \"{self.target}\". Please ensure that the target name is correct.")
            raise e

    def build(self, cli_args: list[str] | None = None):
        """
        Build the Docker container using the Docker compose 'build' command.

        Args:
            cli_args: None by default, or a list with a string containing cli args for 'docker compose build'
        """
        print(f"[INFO] Building the docker image {self.image_name}...")
        if cli_args is None:
            cli_args = []
        else:
            cli_args = cli_args[0].split(" ")
        try:
            subprocess.run(
                ["docker", "compose"] + self.add_yamls() + self.add_env_files() + ["build"] + cli_args,
                check=True,
                cwd=self.dir,
                env=self.environ,
            )
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Unable to 'build' target \"{self.target}\". Please ensure that the target name is correct.")
            raise e

    def enter(self):
        """
        Enter the running container by executing a bash shell.

        Raises:
            RuntimeError: If the container is not running.
        """
        if self.is_container_running():
            print(f"[INFO] Entering the existing {self.container_name} container in a bash session...")
            try:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "--interactive",
                        "--tty",
                        "-e",
                        f"DISPLAY={os.getenv('DISPLAY')}",
                        f"{self.container_name}",
                        "bash",
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Unable to 'enter' container \"{self.container_name}\", though it seems to be running.")
                raise e
        else:
            raise RuntimeError(
                f"The container '{self.container_name}' is not running. Please ensure target name \"{self.target}\" is"
                " correct."
            )

    def stop(self):
        """
        Stop the running container using the Docker compose command.

        Raises:
            RuntimeError: If the container is not running.
        """
        if self.is_container_running():
            print(f"[INFO] Stopping the launched docker container {self.container_name}...")
            try:
                subprocess.run(
                    ["docker", "compose"] + self.add_yamls() + self.add_env_files() + ["down"],
                    check=True,
                    cwd=self.dir,
                    env=self.environ,
                )
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Unable to 'stop' container \"{self.container_name}\", though it seems to be running.")
                raise e
        else:
            raise RuntimeError(
                f"Can't stop container '{self.container_name}' as it is not running. Please ensure target name"
                f' "{self.target}" is correct.'
            )

    def copy(self, output_dir: Path | None = None):
        """
        Copy artifacts from the running container to the host machine.

        Args:
            output_dir: The directory to copy the artifacts to. Defaults to self.dir.

        Raises:
            RuntimeError: If the container is not running.
        """
        if self.is_container_running():
            print(f"[INFO] Copying artifacts from the 'isaac-lab-{self.container_name}' container...")
            if output_dir is None:
                output_dir = self.dir
            output_dir = output_dir.joinpath("artifacts")
            if not output_dir.is_dir():
                output_dir.mkdir()
            artifacts = {
                Path(self.dot_vars["DOCKER_ISAACLAB_PATH"]).joinpath("logs"): output_dir.joinpath("logs"),
                Path(self.dot_vars["DOCKER_ISAACLAB_PATH"]).joinpath("docs/_build"): output_dir.joinpath("docs"),
                Path(self.dot_vars["DOCKER_ISAACLAB_PATH"]).joinpath("data_storage"): output_dir.joinpath(
                    "data_storage"
                ),
            }
            for container_path, host_path in artifacts.items():
                print(f"\t -{container_path} -> {host_path}")
            for path in artifacts.values():
                shutil.rmtree(path, ignore_errors=True)
            for container_path, host_path in artifacts.items():
                try:
                    subprocess.run(
                        [
                            "docker",
                            "cp",
                            f"isaac-lab-{self.target}:{container_path}/",
                            f"{host_path}",
                        ],
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(
                        f"[ERROR] Unable to 'copy' from container \"{self.container_name}\", though it seems to be"
                        " running."
                    )
                    raise e
            print("\n[INFO] Finished copying the artifacts from the container.")
        else:
            raise RuntimeError(
                f"The container '{self.container_name}' is not running. Please ensure target name \"{self.target}\" is"
                " correct."
            )

    def config(self, output_yaml: Path | None = None):
        """
        Generate a docker-compose.yaml from the passed yamls, .envs, and either print to the
        terminal or create a yaml at output_yaml

        Args:
            output_yaml: The absolute path of the yaml file to write the output to, if any. Defaults
            to None, and simply prints to the terminal
        """
        print("[INFO] Configuring the passed options into a yaml...")
        if output_yaml is not None:
            output = ["--output", output_yaml]
        else:
            output = []
        try:
            subprocess.run(
                ["docker", "compose"] + self.add_yamls() + self.add_env_files() + ["config"] + output,
                check=True,
                cwd=self.dir,
                env=self.environ,
            )
        except subprocess.CalledProcessError as e:
            print(
                f'[ERROR] Unable to generate config from target "{self.target}". Please ensure that the target name is'
                " correct."
            )
            raise e

    def search_compose_cfgs(self, file: Path, required: bool = True) -> Path | None:
        """
        Search the self.yamls_dir directory for 'file'. If required=True and
        the file is not found, throw an error. Does nothing if the file is absolute.

        Args:
            file: File to search for
            required: Whether to throw an error if the file is not found

        Raises:
            FileNotFoundError: If the file is not found
        """
        # Return if path to file is
        # absolute and file exists
        if os.path.isabs(file):
            if os.path.isfile(file):
                return file
            if required:
                raise FileNotFoundError(
                    "The absolute path to required file {file} was passed, but the file does not exist"
                )

        # Brute force search self.yamls_dir if the hint path failed
        for root, _, files in os.walk(self.yamls_dir):
            if file in files:
                return os.path.abspath(os.path.join(root, file))

        if required:
            raise FileNotFoundError(f"Couldn't find required {file} under the compose_cfgs directory {self.yamls_dir}")
        return None
