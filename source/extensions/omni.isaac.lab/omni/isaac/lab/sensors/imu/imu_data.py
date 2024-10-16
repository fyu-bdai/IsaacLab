# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import torch
from dataclasses import dataclass


@dataclass
class ImuData:
    """Data container for the Imu sensor."""

    pos_w: torch.Tensor = None
    """Position of the sensor origin in world frame.

    Shape is (N, 3), where ``N`` is the number of environments.
    """

    quat_w: torch.Tensor = None
    """Orientation of the sensor origin in quaternion ``(w, x, y, z)`` in world frame.

    Shape is (N, 4), where ``N`` is the number of environments.
    """

    lin_vel_b: torch.Tensor = None
    """IMU linear velocity relative to the world expressed in imu frame.

    Shape is (N, 3), where ``N`` is the number of environments.
    """

    ang_vel_b: torch.Tensor = None
    """IMU angular velocity relative to the world frame expressed in imu frame.

    Shape is (N, 3), where ``N`` is the number of environments.
    """

    lin_acc_b: torch.Tensor = None
    """IMU linear acceleration relative to the world frame expressed in imu frame.

    Shape is (N, 3), where ``N`` is the number of environments.
    """

    ang_acc_b: torch.Tensor = None
    """IMU angular acceleration relative to the world frame expressed in imu frame.

    Shape is (N, 3), where ``N`` is the number of environments.
    """
