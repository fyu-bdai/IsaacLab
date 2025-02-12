#!/usr/bin/env python3

# Copyright (c) 2022-2025, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import shutil
from pathlib import Path

from utils import x11_utils
from utils.isaaclab_container_interface import IsaacLabContainerInterface


def main():
    parser = argparse.ArgumentParser(description="Utility for using Docker with Isaac Lab.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # We have to create separate parent parsers for common options to our subparsers
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "target", nargs="?", default="base", help="Optional container target specification. Defaults to 'base'."
    )
    parent_parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help=(
            "Allows additional .yaml files to be passed to the docker compose command. Files will be merged with"
            " docker-compose.yaml in the order in which they are provided."
        ),
    )
    parent_parser.add_argument(
        "--env-files",
        nargs="*",
        default=None,
        help=(
            "Allows additional .env files to be passed to the docker compose command. Files will be merged with"
            " .env.base in the order in which they are provided."
        ),
    )

    # Subparsers for 'build' and 'up', also passed to 'start'
    build_opts_parser = argparse.ArgumentParser(add_help=False)
    build_opts_parser.add_argument(
        "--build-args", nargs="*", type=str, help="Optional options to append to `docker compose build` command."
    )

    up_opts_parser = argparse.ArgumentParser(add_help=False)
    up_opts_parser.add_argument(
        "--up-args", nargs="*", type=str, help="Optional options to append to `docker compose up` command."
    )

    # Actual command definition begins here
    subparsers.add_parser(
        "start",
        help="Build the docker image and bring up the compose network in detached mode.",
        parents=[parent_parser, build_opts_parser, up_opts_parser],
    )
    subparsers.add_parser(
        "build",
        help="Build the docker image.",
        parents=[parent_parser, build_opts_parser],
    )
    subparsers.add_parser(
        "copy", help="Copy build and logs artifacts from the container to the host machine.", parents=[parent_parser]
    )
    config = subparsers.add_parser(
        "config",
        help=(
            "Generate a docker-compose.yaml from the passed yamls, .envs, and either print to the terminal or create a"
            " yaml at output_yaml"
        ),
        parents=[parent_parser],
    )
    config.add_argument(
        "--output-yaml", nargs="?", default=None, help="Yaml file to write config output to. Defaults to None."
    )
    subparsers.add_parser(
        "enter", help="Begin a new bash process within an existing Isaac Lab container.", parents=[parent_parser]
    )
    subparsers.add_parser("stop", help="Stop the docker container and remove it.", parents=[parent_parser])

    args = parser.parse_args()

    if not shutil.which("docker"):
        raise RuntimeError("Docker is not installed! Please check the 'Docker Guide' for instruction.")

    # Creating container interface
    ci = IsaacLabContainerInterface(
        dir=Path(__file__).resolve().parent,
        target=args.target,
        yamls=args.files,
        envs=args.env_files,
    )

    print(f"[INFO] Using container target: {ci.target}")
    if args.command == "start":
        print(f"[INFO] Building the docker image and starting the container {ci.container_name} in the background...")
        x11_outputs = x11_utils.x11_check(ci.statefile)
        if x11_outputs is not None:
            (x11_yaml, x11_envar) = x11_outputs
            ci.yamls += x11_yaml
            ci.environ.update(x11_envar)
        ci.build(args.build_args)
        ci.up(args.up_args)
    elif args.command == "build":
        ci.build(args.build_args)
    elif args.command == "config":
        ci.config(args.output_yaml)
    elif args.command == "copy":
        ci.copy()
    elif args.command == "enter":
        x11_utils.x11_refresh(ci.statefile)
        ci.enter()
    elif args.command == "stop":
        ci.stop()
        x11_utils.x11_cleanup(ci.statefile)
    else:
        raise RuntimeError(f"Invalid command provided: {args.command}")


if __name__ == "__main__":
    main()
