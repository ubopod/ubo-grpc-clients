"""Client for the remote store."""

from __future__ import annotations

import base64
import grpclib.exceptions
import sys
from typing import TYPE_CHECKING, overload

from grpclib.client import Channel
# from PIL import Image

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

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 50051


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


async def connect() -> None:
    """Connect to the gRPC server."""
    store = AsyncRemoteStore(SERVER_HOST, SERVER_PORT)
    notification_action_items = [
        NotificationActionsItem(
            notification_dispatch_item=NotificationDispatchItem(
                label="custom action",
                color="#ff0000",
                background_color="#00ff00",
                icon="󰑣",
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
                    title="Hello",
                    content="World",
                    actions=NotificationActions(
                        items=notification_action_items,
                    ),
                ),
            ),
        ),
    )

    sys.stdout.write("\033[2J\033[H")

    def save_image(event: Event) -> None:
        if event.display_render_event:
            display_render_event = event.display_render_event
            data = display_render_event.data
            # TODO, it needs to take into account the rectangle's position too
            width, height = display_render_event.rectangle[2:]

            image_base64 = base64.b64encode(data).decode("utf-8")
            chunks = [
                image_base64[i : i + 4096] for i in range(0, len(image_base64), 4096)
            ]
            kitty_image_protocol = f"\033_Gm={1 if len(chunks) > 1 else 0},a=T,i=1,q=1,C=1,s={width},v={height};{chunks[0]}\033\\"
            for chunk in chunks[1:-1]:
                kitty_image_protocol += f"\033_Gm=1,q=1;{chunk}\033\\"
            if len(chunks) > 1:
                kitty_image_protocol += f"\033_Gm=0,q=1;{chunks[-1]}\033\\"

            sys.stdout.write(kitty_image_protocol)
            sys.stdout.flush()

    await store.subscribe_event(
        Event(display_render_event=DisplayRenderEvent()),
        save_image,
    )
    store.channel.close()


def main() -> None:
    try:
        import asyncio

        asyncio.run(connect())
    except KeyboardInterrupt:
        print("\n" * 8)
        print("KeyboardInterrupt.")
    except grpclib.exceptions.StreamTerminatedError:
        print("\n" * 8)
        print("StreamTerminatedError.")
