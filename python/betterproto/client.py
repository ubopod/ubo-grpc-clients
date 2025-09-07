"""Client for the remote store."""

from __future__ import annotations

import asyncio
import base64
import fcntl
import os
import select
import sys
import termios
import time
import tty
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, overload

import grpclib.exceptions
import numpy as np
import pyaudio
from grpclib.client import Channel

from generated.store.v1 import (
    DispatchActionRequest,
    DispatchEventRequest,
    StoreServiceStub,
    SubscribeEventRequest,
)
from generated.ubo.v1 import (
    Action,
    AssistantStartListeningAction,
    AssistantStopListeningAction,
    AudioPlayRecordingAction,
    AudioReportSampleAction,
    AudioSample,
    AudioStartRecordingAction,
    AudioStopRecordingAction,
    DisplayRedrawAction,
    DisplayRenderEvent,
    Event,
    Key,
    KeypadKeyPressAction,
    KeypadKeyPressActionPressedKeysSetType,
    KeypadKeyReleaseAction,
    Notification,
    NotificationActions,
    NotificationActionsItem,
    NotificationDispatchItem,
    NotificationDispatchItemStoreAction,
    NotificationsAddAction,
)

if TYPE_CHECKING:
    from collections.abc import Callable

SERVER_HOST = os.environ.get('GRPC_HOST', 'localhost')
SERVER_PORT = int(os.environ.get('GRPC_PORT', '50051'))

WIDTH = 240
HEIGHT = 240
MARGIN = 50

INPUT_FRAME_RATE = 16_000
INPUT_CHANNELS = 1
INPUT_PERIOD_SIZE = int(INPUT_FRAME_RATE / 1000) * 20  # 20ms


class AsyncRemoteStore:
    """Async remote store for dispatching operations to a gRPC server."""

    def __init__(
        self: AsyncRemoteStore,
        host: str,
        port: int,
    ) -> None:
        """Initialize the async remote store."""
        self.channel = Channel(host=host, port=port)
        self.service = StoreServiceStub(self.channel)

    @overload
    async def dispatch_async(
        self: AsyncRemoteStore,
        *,
        action: Action,
    ) -> None: ...
    @overload
    async def dispatch_async(
        self: AsyncRemoteStore,
        *,
        event: Event,
    ) -> None: ...
    async def dispatch_async(
        self: AsyncRemoteStore,
        *,
        action: Action | None = None,
        event: Event | None = None,
    ) -> None:
        """Dispatch an operation to the remote store."""
        if action is not None:
            await self.service.dispatch_action(DispatchActionRequest(action=action))
        if event is not None:
            await self.service.dispatch_event(DispatchEventRequest(event=event))

    async def subscribe_event(
        self: AsyncRemoteStore,
        event_type: Event,
        callback: Callable[[Event], None],
    ) -> None:
        """Subscribe to the remote store."""
        async for response in self.service.subscribe_event(
            SubscribeEventRequest(event=event_type),
        ):
            callback(response.event)


def _is_kitty_supported() -> tuple[tuple[int, int], tuple[int, int]] | None:
    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)
    new_term = termios.tcgetattr(fd)
    new_term[3] = new_term[3] & ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(fd, termios.TCSANOW, new_term)
    old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)
    try:
        sys.stdout.write('\033_Gi=1,a=q,s=1,v=1,f=24;AAAA\033\\')
        sys.stdout.flush()
        response = b''
        while True:
            rlist, _, _ = select.select([fd], [], [], 1)
            if fd in rlist:
                try:
                    chunk = os.read(fd, 1024)
                    if not chunk:
                        break
                    response += chunk
                except OSError:
                    break
            else:
                break
        if b';OK' in response:
            tty.setraw(fd)
            # Get pixel size
            sys.stdout.write('\033[14t')
            sys.stdout.flush()
            pixel_response = b''
            while True:
                rlist, _, _ = select.select([fd], [], [], 1)
                if fd in rlist:
                    try:
                        chunk = os.read(fd, 1024)
                        if not chunk:
                            break
                        pixel_response += chunk
                    except OSError:
                        break
                else:
                    break
            # Get block size
            sys.stdout.write('\033[18t')
            sys.stdout.flush()
            block_response = b''
            while True:
                rlist, _, _ = select.select([fd], [], [], 1)
                if fd in rlist:
                    try:
                        chunk = os.read(fd, 1024)
                        if not chunk:
                            break
                        block_response += chunk
                    except OSError:
                        break
                else:
                    break
            pixel_str = pixel_response.decode()
            block_str = block_response.decode()
            if pixel_str.startswith('\033[4;') and block_str.startswith('\033[8;'):
                pixel_parts = pixel_str[2:].split(';')
                block_parts = block_str[2:].split(';')
                if (
                    len(pixel_parts) >= 3  # noqa: PLR2004
                    and pixel_parts[2].endswith('t')
                    and len(block_parts) >= 3  # noqa: PLR2004
                    and block_parts[2].endswith('t')
                ):
                    pixel_height, pixel_width = pixel_parts[1], pixel_parts[2][:-1]
                    rows, cols = block_parts[1], block_parts[2][:-1]
                    return (
                        (int(pixel_width), int(pixel_height)),
                        (int(cols), int(rows)),
                    )
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_term)
        fcntl.fcntl(fd, fcntl.F_SETFL, old_flags)


kitty_size = _is_kitty_supported()
is_kitty_supported = kitty_size is not None
is_iterm2_supported = os.environ.get('TERM_PROGRAM') == 'iTerm.app'


class Display:
    def __init__(self: Display, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width = 0
        self.height = 0
        self.resize(width, height)

    def resize(self: Display, width: int, height: int) -> None:
        if self.width != width + MARGIN * 2 or self.height != height + MARGIN * 2:
            self.width = width + MARGIN * 2
            self.height = height + MARGIN * 2
            self.buffer = bytearray(self.width * self.height * 4)
            self.buffer[:] = b'\x00\x00\x00\x00' * self.width * self.height


display = Display()


def render_in_kitty(event: Event) -> None:
    if event.display_render_event and kitty_size:
        display_render_event = event.display_render_event
        data = display_render_event.data
        y1, x1, y2, x2 = display_render_event.rectangle
        width, height = x2 - x1, y2 - y1

        x1 += MARGIN
        y1 += MARGIN

        new_width = int(event.display_render_event.density * WIDTH)
        new_height = int(event.display_render_event.density * HEIGHT)

        display.resize(new_width, new_height)

        image_x = (
            (kitty_size[0][0] - display.width)
            * kitty_size[1][0]
            // kitty_size[0][0]
            // 2
        )
        image_y = (
            (kitty_size[0][1] - display.height)
            * kitty_size[1][1]
            // kitty_size[0][1]
            // 2
        )

        for row in range(height):
            src_start = row * width * 4
            src_end = src_start + width * 4
            dst_start = ((y1 + row) * display.width + x1) * 4
            dst_end = dst_start + width * 4
            display.buffer[dst_start:dst_end] = data[src_start:src_end]

        image_base64 = base64.b64encode(display.buffer).decode('utf-8')
        chunks = [image_base64[i : i + 4096] for i in range(0, len(image_base64), 4096)]
        kitty_image_protocol = f'\033_Gm={1 if len(chunks) > 1 else 0},a=T,i=1'
        kitty_image_protocol += (
            f',f=32,q=1,C=1,s={display.width},v={display.height};{chunks[0]}\033\\'
        )
        for chunk in chunks[1:-1]:
            kitty_image_protocol += f'\033_Gm=1,q=1;{chunk}\033\\'
        if len(chunks) > 1:
            kitty_image_protocol += f'\033_Gm=0,q=1;{chunks[-1]}\033\\'

        sys.stdout.write(f'\033[{image_y + 1};{image_x + 1}H')
        sys.stdout.write(kitty_image_protocol)
        sys.stdout.flush()


def render_in_iterm(event: Event) -> None:
    if event.display_render_event:
        display_render_event = event.display_render_event
        data = display_render_event.data
        width, height = display_render_event.rectangle[2:]

        pam_header = f'P7\nWIDTH {width}\nHEIGHT {height}\nDEPTH 4\n'
        pam_header += 'MAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n'
        pam_data = pam_header.encode('ascii') + data
        img_base64 = base64.b64encode(pam_data).decode('utf-8')

        sys.stdout.write('\033[H')
        sys.stdout.write(
            f'\033]1337;File=inline=1;width={width}px;height={height}px;size={len(img_base64)}:{img_base64}\a\n',
        )
        sys.stdout.flush()


store = AsyncRemoteStore(SERVER_HOST, SERVER_PORT)


async def connect() -> None:
    """Connect to the gRPC server."""
    if is_kitty_supported:
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()
        render_image_ = render_in_kitty
    elif is_iterm2_supported:
        sys.stdout.write('\033[2J\033[H')
        render_image_ = render_in_iterm
    else:
        print('Saving display in `display.raw`')
        print(
            'Run in a terminal supporting iTerm2 or Kitty image display to see the '
            'screen in your terminal.',
        )

        last_write = 0

        def render_image_(event: Event) -> None:
            nonlocal last_write
            if last_write + 2 < time.time():
                last_write = time.time()
                return
            if event.display_render_event:
                display_render_event = event.display_render_event
                data = display_render_event.data

                with Path('display.raw').open('wb') as file:
                    file.write(data)

    def render_image(event: Event) -> None:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, render_image_, event)

    await store.subscribe_event(
        Event(display_render_event=DisplayRenderEvent()),
        render_image,
    )


async def schedule_redraw() -> None:
    await asyncio.sleep(0.1)
    await store.dispatch_async(
        action=Action(display_redraw_action=DisplayRedrawAction()),
    )


KEY_ACTIONS = {
    '1': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.L1,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.L1],
            ),
            time=0.0,
        ),
    ),
    '2': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.L2,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.L2],
            ),
            time=0.0,
        ),
    ),
    '3': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.L3,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.L3],
            ),
            time=0.0,
        ),
    ),
    '\x7f': Action(
        keypad_key_release_action=KeypadKeyReleaseAction(
            key=Key.HOME,
            time=0.0,
        ),
    ),
    '\33[D': Action(
        keypad_key_release_action=KeypadKeyReleaseAction(
            key=Key.BACK,
            time=0.0,
        ),
    ),
    'h': Action(
        keypad_key_release_action=KeypadKeyReleaseAction(
            key=Key.BACK,
            time=0.0,
        ),
    ),
    '\33[A': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.UP,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.UP],
            ),
            time=0.0,
        ),
    ),
    'k': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.UP,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.UP],
            ),
            time=0.0,
        ),
    ),
    '\33[B': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.DOWN,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.DOWN],
            ),
            time=0.0,
        ),
    ),
    'j': Action(
        keypad_key_press_action=KeypadKeyPressAction(
            key=Key.DOWN,
            pressed_keys=KeypadKeyPressActionPressedKeysSetType(
                items=[Key.DOWN],
            ),
            time=0.0,
        ),
    ),
    'r': Action(
        audio_start_recording_action=AudioStartRecordingAction(),
    ),
    's': Action(
        audio_stop_recording_action=AudioStopRecordingAction(),
    ),
    'p': Action(
        audio_play_recording_action=AudioPlayRecordingAction(),
    ),
    'n': Action(
        notifications_add_action=NotificationsAddAction(
            notification=Notification(
                title='Hello',
                content='betterproto RPC client connected.',
                actions=NotificationActions(
                    items=[
                        NotificationActionsItem(
                            notification_dispatch_item=NotificationDispatchItem(
                                label='custom action',
                                color='#ff0000',
                                background_color='#00ff00',
                                icon='󰑣',
                                store_action=NotificationDispatchItemStoreAction(
                                    ubo_action=Action(
                                        keypad_key_press_action=KeypadKeyPressAction(
                                            key=Key.HOME,
                                            time=0.0,
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ],
                ),
            ),
        ),
    ),
    'v': Action(assistant_start_listening_action=AssistantStartListeningAction()),
    'V': Action(assistant_stop_listening_action=AssistantStopListeningAction()),
}


async def handle_keyboard() -> None:
    loop = asyncio.get_event_loop()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        sequence = ''
        while True:
            key = await loop.run_in_executor(None, sys.stdin.read, 1)
            sequence += key
            for key in sorted(KEY_ACTIONS, key=lambda key: len(key)):
                if sequence.endswith(key):
                    await store.dispatch_async(action=KEY_ACTIONS[key])
                    sequence = ''
                    continue

            if sequence.endswith('q'):
                sys.exit(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def stream_mic() -> None:
    pa = pyaudio.PyAudio()
    event_loop = asyncio.get_event_loop()

    try:
        channels_ = pa.get_default_input_device_info()['maxInputChannels']
        if not isinstance(channels_, int) or channels_ < 1:

            async def read_audio_chunk() -> tuple[int, bytes, int]:
                await asyncio.sleep(0.1)
                return 0, b'', 1
        else:
            channels = channels_
            read_executor = ThreadPoolExecutor(max_workers=1)
            input_audio = pa.open(
                format=pyaudio.paInt16,
                channels=INPUT_CHANNELS,
                rate=INPUT_FRAME_RATE,
                input=True,
                frames_per_buffer=INPUT_PERIOD_SIZE,
            )

            async def read_audio_chunk() -> tuple[int, bytes, int]:
                data = await event_loop.run_in_executor(
                    read_executor,
                    input_audio.read,
                    INPUT_PERIOD_SIZE,
                    False,  # noqa: FBT003
                )
                return len(data), data, channels
    except OSError:
        print('Audio - Error opening audio capture')

        async def read_audio_chunk() -> tuple[int, bytes, int]:
            await asyncio.sleep(0.1)
            return 0, b'', 1

    loop = asyncio.get_event_loop()
    tasks = []

    while True:
        length, data, channels = await read_audio_chunk()
        if length > 0:
            data_speech_recognition = np.frombuffer(data, dtype=np.int16)
            data_speech_recognition = data_speech_recognition.reshape(
                -1,
                channels,
            )
            data_speech_recognition = data_speech_recognition.T
            data_speech_recognition = (
                data_speech_recognition.astype(np.float32) / 32768.0
            )

            data_speech_recognition = data_speech_recognition.squeeze()

            data_speech_recognition = (
                (data_speech_recognition * 32768.0).astype(np.int16).tobytes()
            )
            tasks.append(
                loop.create_task(
                    store.dispatch_async(
                        action=Action(
                            audio_report_sample_action=AudioReportSampleAction(
                                timestamp=event_loop.time(),
                                sample_speech_recognition=data_speech_recognition,
                                sample=AudioSample(
                                    data=data,
                                    channels=channels,
                                    rate=INPUT_FRAME_RATE,
                                    width=2,
                                ),
                            ),
                        ),
                    ),
                ),
            )


def app() -> None:
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            asyncio.wait(
                [
                    loop.create_task(handle_keyboard()),
                    loop.create_task(connect()),
                    loop.create_task(stream_mic()),
                    loop.create_task(schedule_redraw()),
                ],
                return_when=asyncio.ALL_COMPLETED,
            ),
        )
    except KeyboardInterrupt:
        print('\n' * 9 + 'KeyboardInterrupt.')
        return
    except grpclib.exceptions.StreamTerminatedError:
        print('\n' * 9 + 'StreamTerminatedError.')
    else:
        print('\n' * 9)
    finally:
        store.channel.close()


def main() -> None:
    app()
