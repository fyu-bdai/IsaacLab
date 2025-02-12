.. _deployment-docker:


Docker Guide
============

.. caution::

    Due to the dependency on Isaac Sim docker image, by running this container you are implicitly
    agreeing to the `NVIDIA Omniverse EULA`_. If you do not agree to the EULA, do not run this container.

Setup Instructions
------------------

.. note::

    The following steps are taken from the NVIDIA Omniverse Isaac Sim documentation on `container installation`_.
    They have been added here for the sake of completeness.


Docker and Docker Compose
~~~~~~~~~~~~~~~~~~~~~~~~~

We have tested the container using Docker Engine version 26.0.0 and Docker Compose version 2.25.0
We recommend using these versions or newer.

* To install Docker, please follow the instructions for your operating system on the `Docker website`_.
* To install Docker Compose, please follow the instructions for your operating system on the `docker compose`_ page.
* Follow the post-installation steps for Docker on the `post-installation steps`_ page. These steps allow you to run
  Docker without using ``sudo``.
* To build and run GPU-accelerated containers, you also need install the `NVIDIA Container Toolkit`_.
  Please follow the instructions on the `Container Toolkit website`_ for installation steps.

.. note::

    Due to limitations with `snap <https://snapcraft.io/docs/home-outside-home>`_, please make sure
    the Isaac Lab directory is placed under the ``/home`` directory tree when using docker.


Obtaining the Isaac Sim Container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Get access to the `Isaac Sim container`_ by joining the NVIDIA Developer Program credentials.
* Generate your `NGC API key`_ to access locked container images from NVIDIA GPU Cloud (NGC).

  * This step requires you to create an NGC account if you do not already have one.
  * You would also need to install the NGC CLI to perform operations from the command line.
  * Once you have your generated API key and have installed the NGC CLI, you need to log in to NGC
    from the terminal.

    .. code:: bash

        ngc config set

* Use the command line to pull the Isaac Sim container image from NGC.

  .. code:: bash

      docker login nvcr.io

  * For the username, enter ``$oauthtoken`` exactly as shown. It is a special username that is used to
    authenticate with NGC.

    .. code:: text

        Username: $oauthtoken
        Password: <Your NGC API Key>


Directory Organization
----------------------

The root of the Isaac Lab repository contains the ``docker`` directory that has various files, scripts and subdirectories
needed to run Isaac Lab inside a Docker container. A subset of these are summarized below:

* ``Dockerfile``: Defines multiple stages for IsaacLab usage, and builds up to ``stage`` defined by the ``TARGET`` in
  ``yamls/base.yaml``.

  * The ``base`` stage overlays Isaac Lab dependencies onto the Isaac Sim Docker image and installs included rl_frameworks
    and core IsaacLab extensions.
  * The ``ros2`` stage adds an installation of ROS2 and attempts to install the rosdeps of any extension under ``/IsaacLab/source/extensions`` with
    ``[isaac_lab_settings.ros_ws]`` defined in their ``config/extension.toml``.
* ``.env``: Stores certain environment variables which are widely used across various ``yamls`` and are centrally defined here and loaded for interpolation
  in possible passthrough in ``yamls``.
* ``container.py``: A script that interfaces with tools in ``isaaclab_container_utils`` to configure and build the image,
  and run and interact with the container.
* ``yamls/``: A set of ``yamls`` which provide a framework for building and running the images defined in ``Dockerfile``. For each ``stage`` within
  the ``Dockerfile``, each yaml supplies the relevant arguments in correspondingly named yaml files (``base.yaml``, ``ros2.yaml``). These provide basic runtime configuration
  such as GPU access, mounts and volumes, as well as environment variables used at build and runtime. The ``stages`` which build upon each other in the Dockerfile (such as ``ros2`` upon ``base``)
  are likewise reflected in the ``extends`` directive of their yamls. There are also snippets such as ``x11.yaml`` and ``isaaclab_volumes.yaml`` which are not valid
  ``docker-compose.yaml`` files on their own and are separated out to make them optional or more portable.


Running the Container
---------------------

.. note::

    The docker container copies all the files from the repository into the container at the
    location ``/workspace/isaaclab`` at build time. This means that any changes made to the files in the container would not
    normally be reflected in the repository after the image has been built, i.e. after ``./container.py start`` is run.

    For a faster development cycle, we mount the following directories in the Isaac Lab repository into the container
    so that you can edit their files from the host machine:

    * **IsaacLab/source**: This is the directory that contains the Isaac Lab source code.
    * **IsaacLab/docs**: This is the directory that contains the source code for Isaac Lab documentation. This is overlaid except
      for the ``_build`` subdirectory where build artifacts are stored.


The script ``container.py`` parallels several ``docker compose`` commands. Each can accept a ``target``,
or else they will default to target ``base``:

1. ``start``: This builds the image and brings up the container in detached mode (i.e. in the background).
2. ``build``: This builds the image but does not bring it up.
3. ``copy``: This copies the ``logs``, ``data_storage`` and ``docs/_build`` artifacts, from the ``isaac-lab-logs``, ``isaac-lab-data`` and ``isaac-lab-docs``
   volumes respectively, to the ``docker/artifacts`` directory. These artifacts persist between docker container instances and are shared between image extensions.
4. ``config``: This will output the resolved ``docker-compose.yaml`` which will be the output of a call to ``container.py``. It is useful for debugging.
5. ``enter``: This begins a new bash process in an existing isaaclab container, and which can be exited without bringing down the container.
6. ``stop``: This brings down the container and removes it.

The following shows how to launch the container in a detached state and enter it:

.. code:: bash

    # Launch the container in detached mode
    # We don't pass an image extension arg, so it defaults to 'base'
    python docker/container.py start
    # Enter the container
    # We pass 'base' explicitly, but if we hadn't it would default to 'base'
    python docker/container.py enter base

To copy files from the base container to the host machine, you can use ``./container.py copy``. This is a
wrapper around ``docker cp`` to copy the ``logs`` , ``data_storage`` and ``docs/_build`` directories to the
``docker/artifacts`` directory. This is useful for copying the logs, data and documentation:

.. code:: bash

    # Copy the file /workspace/isaaclab/logs to the current directory
    docker cp isaac-lab-base:/workspace/isaaclab/logs .

    # Or, you can use 'container.py copy'
    python docker/container.py copy

Lastly, we can bring down the container with the following command:

.. code:: bash

    # stop the container
    python docker/container.py stop


Python Interpreter
~~~~~~~~~~~~~~~~~~

The container uses the Python interpreter provided by Isaac Sim. This interpreter is located at
``/isaac-sim/python.sh``. We set aliases inside the container to make it easier to run the Python
interpreter. You can use the following commands to run the Python interpreter:

.. code:: bash

    # Run the Python interpreter -> points to /isaac-sim/python.sh
    python


Understanding the mounted volumes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``isaaclab_volumes.yaml`` file creates several named volumes that are mounted to the container in ``base.yaml``.
These are summarized below:

* ``isaac-cache-kit``: This volume is used to store cached Kit resources (``/isaac-sim/kit/cache`` in container)
* ``isaac-cache-ov``: This volume is used to store cached OV resources (``/root/.cache/ov`` in container)
* ``isaac-cache-pip``: This volume is used to store cached pip resources (``/root/.cache/pip`` in container)
* ``isaac-cache-gl``: This volume is used to store cached GLCache resources (``/root/.cache/nvidia/GLCache`` in container)
* ``isaac-cache-compute``: This volume is used to store cached compute resources (``/root/.nv/ComputeCache`` in container)
* ``isaac-logs``: This volume is used to store logs generated by Omniverse. (``/root/.nvidia-omniverse/logs`` in container)
* ``isaac-carb-logs``: This volume is used to store logs generated by carb. (``/isaac-sim/kit/logs/Kit/Isaac-Sim`` in container)
* ``isaac-data``: This volume is used to store data generated by Omniverse. (``/root/.local/share/ov/data`` in container)
* ``isaac-docs``: This volume is used to store documents generated by Omniverse. (``/root/Documents`` in container)
* ``isaac-lab-docs``: This volume is used to store documentation of Isaac Lab when built inside the container. (``/workspace/isaaclab/docs/_build`` in container)
* ``isaac-lab-logs``: This volume is used to store logs generated by Isaac Lab workflows when run inside the container. (``/workspace/isaaclab/logs`` in container)
* ``isaac-lab-data``: This volume is used to store whatever data users may want to preserve between container runs. (``/workspace/isaaclab/data_storage`` in container)

To view the contents of these volumes, you can use the following command:

.. code:: bash

    # list all volumes
    docker volume ls
    # inspect a specific volume, e.g. isaac-cache-kit
    docker volume inspect isaac-cache-kit


Isaac Lab Image Targets
-----------------------

The produced image depends upon the arguments passed to ``container.py start`` and ``container.py stop``. These
commands accept a ``target`` stage as an additional argument, resolved to ``TARGET`` in ``base.yaml``. If no argument is passed,
the default stage is ``base``. Currently, the only valid ``targets`` in IsaacLab are (``base``, ``ros2``).
Only one ``target`` can be passed at a time, and the produced container will be named ``isaac-lab-{TARGET}``.

.. code:: bash

    # start base by default
    python docker/container.py start
    # stop base explicitly
    python docker/container.py stop base
    # start ros2 container
    python docker/container.py start ros2
    # stop ros2 container
    python docker/container.py stop ros2

A ``./container.py start/build`` command passed a ``target`` argument will build the image up to the target stage as
defined in ``Dockerfile``, using the corresponding file under ``yamls/``.

ROS2 Image Target
~~~~~~~~~~~~~~~~~

In ``Dockerfile`` stage ``ros2``, the container installs ROS2 Humble via an `apt package`_, and it is sourced in the ``.bashrc``.
The exact version is specified by the variable ``ROS_APT_PACKAGE`` in the ``ros2.yaml`` file,
defaulting to ``ros-base``. Other relevant ROS2 variables are also specified with ENVs in the ``Dockerfile``,
including variables defining the `various middleware`_ options. The container defaults to ``FastRTPS``, but ``CylconeDDS``
is also supported. Each of these middlewares can be `tuned`_ using their corresponding ``.xml`` files under ``docker/.ros``.


Known Issues
------------

WebRTC Streaming
~~~~~~~~~~~~~~~~

When streaming the GUI from Isaac Sim, there are `several streaming clients`_ available. There is a `known issue`_ when
attempting to use WebRTC streaming client on Google Chrome and Safari while running Isaac Sim inside a container.
To avoid this problem, we suggest using the Native Streaming Client or using the
Mozilla Firefox browser on which WebRTC works.

Streaming is the only supported method for visualizing the Isaac GUI from within the container. The Omniverse Streaming Client
is freely available from the Omniverse app, and is easy to use. The other streaming methods similarly require only a web browser.
If users want to use X11 forwarding in order to have the apps behave as local GUI windows, they can uncomment the relevant portions
in docker-compose.yaml.


.. _`NVIDIA Omniverse EULA`: https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html
.. _`container installation`: https://docs.omniverse.nvidia.com/isaacsim/latest/installation/install_container.html
.. _`Docker website`: https://docs.docker.com/desktop/install/linux-install/
.. _`docker compose`: https://docs.docker.com/compose/install/linux/#install-using-the-repository
.. _`NVIDIA Container Toolkit`: https://github.com/NVIDIA/nvidia-container-toolkit
.. _`Container Toolkit website`: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
.. _`post-installation steps`: https://docs.docker.com/engine/install/linux-postinstall/
.. _`Isaac Sim container`: https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-sim
.. _`NGC API key`: https://docs.nvidia.com/ngc/gpu-cloud/ngc-user-guide/index.html#generating-api-key
.. _`several streaming clients`: https://docs.omniverse.nvidia.com/isaacsim/latest/installation/manual_livestream_clients.html
.. _`known issue`: https://forums.developer.nvidia.com/t/unable-to-use-webrtc-when-i-run-runheadless-webrtc-sh-in-remote-headless-container/222916
.. _`profile`: https://docs.docker.com/compose/compose-file/15-profiles/
.. _`apt package`: https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html#install-ros-2-packages
.. _`various middleware`: https://docs.ros.org/en/humble/How-To-Guides/Working-with-multiple-RMW-implementations.html
.. _`tuned`: https://docs.ros.org/en/foxy/How-To-Guides/DDS-tuning.html
