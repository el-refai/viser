"""Record3D visualizer

Parse and stream record3d captures. To get the demo data, see `./assets/download_record3d_dance.sh`.
"""

import time
from pathlib import Path
from typing import List

import numpy as onp
import tyro
from tqdm.auto import tqdm

import viser
import viser.transforms as tf


def main(
    data_path: Path = Path(__file__).parent / "assets/record3d_dance",
    downsample_factor: int = 2,
    max_frames: int = 50,
) -> None:
    server = viser.ViserServer()

    print("Loading frames!")
    loader = viser.extras.Record3dLoader(data_path)
    num_frames = min(max_frames, loader.num_frames())

    # Add playback UI.
    with server.gui_folder("Playback"):
        gui_timestep = server.add_gui_slider(
            "Timestep", min=0, max=num_frames - 1, step=1, initial_value=0
        )
        gui_next_frame = server.add_gui_button("Next Frame")
        gui_prev_frame = server.add_gui_button("Prev Frame")
        gui_playing = server.add_gui_checkbox("Playing", False)
        gui_framerate = server.add_gui_slider(
            "FPS", min=1, max=60, step=0.1, initial_value=loader.fps
        )

    # Frame step buttons.
    @gui_next_frame.on_click
    def _(_) -> None:
        gui_timestep.value = (gui_timestep.value + 1) % num_frames

    @gui_prev_frame.on_click
    def _(_) -> None:
        gui_timestep.value = (gui_timestep.value - 1) % num_frames

    # Disable frame controls when we're playing.
    @gui_playing.on_update
    def _(_) -> None:
        gui_timestep.disabled = gui_playing.value
        gui_next_frame.disabled = gui_playing.value
        gui_prev_frame.disabled = gui_playing.value

    prev_timestep = gui_timestep.value

    # Toggle frame visibility when the timestep slider changes.
    @gui_timestep.on_update
    def _(_) -> None:
        nonlocal prev_timestep
        current_timestep = gui_timestep.value
        with server.atomic():
            frame_nodes[current_timestep].visible = True
            frame_nodes[prev_timestep].visible = False
        prev_timestep = current_timestep

    # Load in frames.
    server.add_frame(
        "/frames",
        wxyz=tf.SO3.exp(onp.array([onp.pi / 2.0, 0.0, 0.0])).wxyz,
        position=(0, 0, 0),
        show_axes=False,
    )
    frame_nodes: List[viser.SceneNodeHandle] = []
    for i in tqdm(range(num_frames)):
        frame = loader.get_frame(i)
        position, color = frame.get_point_cloud(downsample_factor)

        # Add base frame.
        frame_nodes.append(server.add_frame(f"/frames/t{i}", show_axes=False))

        # Place the point cloud in the frame.
        server.add_point_cloud(
            name=f"/frames/t{i}/point_cloud",
            points=position,
            colors=color,
            point_size=0.01,
        )

        # Place the frustum.
        fov = 2 * onp.arctan2(frame.rgb.shape[0] / 2, frame.K[0, 0])
        aspect = frame.rgb.shape[1] / frame.rgb.shape[0]
        frustum = server.add_camera_frustum(
            f"/frames/t{i}/frustum",
            fov=fov,
            aspect=aspect,
            scale=0.15,
        )
        frustum.wxyz = tf.SO3.from_matrix(frame.T_world_camera[:3, :3]).wxyz
        frustum.position = frame.T_world_camera[:3, 3]

        # Add some axes.
        server.add_frame(
            f"/frames/t{i}/frustum/axes",
            axes_length=0.05,
            axes_radius=0.005,
        )

        # Show the captured RGB image, and shift + orient it into the frustum.
        height = 0.15 * onp.tan(fov / 2.0) * 2.0
        img = server.add_image(
            f"/frames/t{i}/frustum/image",
            image=frame.rgb[::downsample_factor, ::downsample_factor],
            render_width=height * aspect,
            render_height=height,
            format="png",
        )
        img.wxyz = tf.SO3.exp(onp.array([onp.pi, 0.0, 0.0])).wxyz
        img.position = onp.array([0.0, 0.0, 0.15])

    # Hide all but the current frame.
    for i, frame_node in enumerate(frame_nodes):
        frame_node.visible = i == gui_timestep.value

    # Playback update loop.
    prev_timestep = gui_timestep.value
    while True:
        if gui_playing.value:
            gui_timestep.value = (gui_timestep.value + 1) % num_frames

        time.sleep(1.0 / gui_framerate.value)


if __name__ == "__main__":
    tyro.cli(main)