"""Client for the remote store."""

from __future__ import annotations

import asyncio
import base64
import fcntl
import os
import select
import sys
import termios
import tty
from pathlib import Path
from typing import TYPE_CHECKING, overload

import grpclib.exceptions
from grpclib.client import Channel

from generated.store.v1 import (
    DispatchActionRequest,
    DispatchEventRequest,
    StoreServiceStub,
    SubscribeEventRequest,
)
from generated.ubo.v1 import (
    Action,
    DisplayRenderEvent,
    Event,
    Key,
    KeypadKeyPressAction,
    Notification,
    NotificationActions,
    NotificationActionsItem,
    NotificationDispatchItem,
    NotificationDispatchItemOperation,
    NotificationsAddAction,
)

if TYPE_CHECKING:
    from collections.abc import Callable

SERVER_HOST = os.environ.get('GRPC_HOST', '127.0.0.1')
SERVER_PORT = int(os.environ.get('GRPC_PORT', '50051'))


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


store = AsyncRemoteStore(SERVER_HOST, SERVER_PORT)


def _is_kitty_supported() -> bool:
    # Save the terminal settings
    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)
    new_term = termios.tcgetattr(fd)
    new_term[3] = new_term[3] & ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(fd, termios.TCSANOW, new_term)

    # Set the terminal to non-blocking mode
    old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)

    try:
        # Send the Kitty query escape sequence
        sys.stdout.write('\033_Gi=1,a=q,s=1,v=1,f=24;AAAA\033\\')
        sys.stdout.flush()

        # Read the response
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

        # Check if the response contains the expected string
        return b';OK' in response
    finally:
        # Restore the terminal settings
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_term)
        fcntl.fcntl(fd, fcntl.F_SETFL, old_flags)


is_kitty_supported = _is_kitty_supported()
is_iterm2_supported = os.environ.get('TERM_PROGRAM') == 'iTerm.app'


def render_in_kitty(event: Event) -> None:
    if event.display_render_event:
        display_render_event = event.display_render_event
        data = display_render_event.data
        # TODO(sassanh): it needs to take into account the rectangle's position
        # too
        width, height = display_render_event.rectangle[2:]

        image_base64 = base64.b64encode(data).decode('utf-8')
        chunks = [image_base64[i : i + 4096] for i in range(0, len(image_base64), 4096)]
        kitty_image_protocol = f'\033_Gm={1 if len(chunks) > 1 else 0},a=T,i=1'
        kitty_image_protocol += f',q=1,C=1,s={width},v={height};{chunks[0]}\033\\'
        for chunk in chunks[1:-1]:
            kitty_image_protocol += f'\033_Gm=1,q=1;{chunk}\033\\'
        if len(chunks) > 1:
            kitty_image_protocol += f'\033_Gm=0,q=1;{chunks[-1]}\033\\'

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


async def connect() -> None:
    """Connect to the gRPC server."""
    notification_action_items = [
        NotificationActionsItem(
            notification_dispatch_item=NotificationDispatchItem(
                label='custom action',
                color='#ff0000',
                background_color='#00ff00',
                icon='󰑣',
                operation=NotificationDispatchItemOperation(
                    ubo_action=Action(
                        keypad_key_press_action=KeypadKeyPressAction(
                            key=Key.HOME,
                            time=0.0,
                        ),
                    ),
                ),
            ),
        ),
    ]
    await store.dispatch_async(
        action=Action(
            notifications_add_action=NotificationsAddAction(
                notification=Notification(
                    title='Hello',
                    content='betterproto RPC client connected.',
                    actions=NotificationActions(
                        items=notification_action_items,
                    ),
                ),
            ),
        ),
    )

    if is_kitty_supported:
        sys.stdout.write('\033[2J\033[H')
        save_image = render_in_kitty
    elif is_iterm2_supported:
        sys.stdout.write('\033[2J\033[H')
        save_image = render_in_iterm
    else:
        print('Saving display in `display.raw`')
        print(
            'Run in a terminal supporting iTerm2 or Kitty image display to see the '
            'screen in your terminal.',
        )

        def save_image(event: Event) -> None:
            if event.display_render_event:
                display_render_event = event.display_render_event
                data = display_render_event.data

                with Path('display.raw').open('wb') as file:
                    file.write(data)

    await store.subscribe_event(
        Event(display_render_event=DisplayRenderEvent()),
        save_image,
    )
    store.channel.close()


KEYS = {
    '1': Key.L1,
    '2': Key.L2,
    '3': Key.L3,
    '\x7f': Key.HOME,
    '\33[D': Key.BACK,
    'h': Key.BACK,
    '\33[A': Key.UP,
    'k': Key.UP,
    '\33[B': Key.DOWN,
    'j': Key.DOWN,
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
            for key in sorted(KEYS, key=lambda key: len(key)):
                if sequence.endswith(key):
                    await store.dispatch_async(
                        action=Action(
                            keypad_key_press_action=KeypadKeyPressAction(
                                key=KEYS[key],
                                time=0.0,
                            ),
                        ),
                    )
                    sequence = ''
                    continue
            if sequence.endswith('q'):
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def app() -> None:
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            asyncio.wait(
                [
                    loop.create_task(handle_keyboard()),
                    loop.create_task(connect()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            ),
        )
    except KeyboardInterrupt:
        print('\n' * 9 + 'KeyboardInterrupt.')
    except grpclib.exceptions.StreamTerminatedError:
        print('\n' * 9 + 'StreamTerminatedError.')
    else:
        print('\n' * 9)


def main() -> None:
    app()
