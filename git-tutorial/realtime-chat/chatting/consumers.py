import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async

from .models import ChatGroup, GroupMessage

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------
#  CHATROOM CONSUMER  (handles sending/receiving chat messages)
# ---------------------------------------------------------------
class ChatroomConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user")

        if not getattr(self.user, "is_authenticated", False):
            await self.close()
            return

        self.chatroom_name = self.scope["url_route"]["kwargs"].get("chatroom_name")
        if not self.chatroom_name:
            await self.close()
            return

        try:
            self.chatroom = await sync_to_async(ChatGroup.objects.get)(
                group_name=self.chatroom_name
            )
        except ChatGroup.DoesNotExist:
            await self.close()
            return

        await self.channel_layer.group_add(self.chatroom_name, self.channel_name)

        user_exists = await sync_to_async(
            self.chatroom.users_online.filter(id=self.user.id).exists
        )()

        if not user_exists:
            await sync_to_async(self.chatroom.users_online.add)(self.user)
            await self.update_online_count()

        await self.accept()

    async def disconnect(self, close_code):
        if not hasattr(self, "chatroom"):
            return

        await self.channel_layer.group_discard(self.chatroom_name, self.channel_name)

        user_exists = await sync_to_async(
            self.chatroom.users_online.filter(id=self.user.id).exists
        )()

        if user_exists:
            await sync_to_async(self.chatroom.users_online.remove)(self.user)
            await self.update_online_count()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "invalid_json"}))
            return

        body = data.get("body")
        if not body:
            await self.send(text_data=json.dumps({"error": "missing_body"}))
            return

        message = await sync_to_async(GroupMessage.objects.create)(
            body=body,
            author=self.user,
            group=self.chatroom
        )

        event = {
            "type": "message_handler",
            "message_id": message.id
        }

        await self.channel_layer.group_send(self.chatroom_name, event)

    async def message_handler(self, event):
        message_id = event.get("message_id")

        try:
            message = await sync_to_async(GroupMessage.objects.get)(id=message_id)
        except GroupMessage.DoesNotExist:
            return

        context = {
            "message": message,
            "user": self.user,
            "chat_group": self.chatroom
        }

        html = await sync_to_async(render_to_string)(
            "a_rtchat/partials/chat_message_p.html",
            context
        )

        payload = {
            "type": "chat_message",
            "message_id": message.id,
            "html": html
        }

        await self.send(text_data=json.dumps(payload))

    async def update_online_count(self):
        total_online = await sync_to_async(self.chatroom.users_online.count)()

        event = {
            "type": "online_count_handler",
            "online_count": total_online
        }

        await self.channel_layer.group_send(self.chatroom_name, event)

    async def online_count_handler(self, event):
        payload = {
            "type": "online_count",
            "online_count": event["online_count"]
        }
        await self.send(text_data=json.dumps(payload))



# ---------------------------------------------------------------
#  ONLINE STATUS CONSUMER  (updates sidebar online list)
# ---------------------------------------------------------------
class OnlineStatusConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user")

        if not getattr(self.user, "is_authenticated", False):
            await self.close()
            return

        self.group_name = "online-status"

        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()
        await self.online_status()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.online_status()

    async def online_status(self):
        event = {"type": "online_status_handler"}
        await self.channel_layer.group_send(self.group_name, event)

    async def online_status_handler(self, event):

        # load public-chat users
        try:
            public_chat = await sync_to_async(ChatGroup.objects.get)(
                group_name="public-chat"
            )
            public_chat_users = await sync_to_async(
                lambda: list(public_chat.users_online.exclude(id=self.user.id))
            )()
        except ChatGroup.DoesNotExist:
            public_chat_users = []

        # Load all chat groups of the user
        try:
            my_chats = await sync_to_async(
                lambda: list(self.user.chat_groups.all())
            )()
        except Exception:
            my_chats = []

        private_chats_with_users = []
        group_chats_with_users = []
        author_ids = set()

        for chat in my_chats:
            try:
                others_exist = await sync_to_async(
                    chat.users_online.exclude(id=self.user.id).exists
                )()

                if others_exist:
                    if getattr(chat, "is_private", False):
                        private_chats_with_users.append(chat)
                    else:
                        group_chats_with_users.append(chat)

                ids = await sync_to_async(
                    lambda: list(chat.users_online.exclude(id=self.user.id)
                                 .values_list("id", flat=True))
                )()
                author_ids.update(ids)

            except Exception:
                pass

        if author_ids:
            online_users = await sync_to_async(
                lambda: list(User.objects.filter(id__in=author_ids))
            )()
        else:
            online_users = []

        online_in_chats = bool(
            public_chat_users or private_chats_with_users or group_chats_with_users
        )

        context = {
            "online_users": online_users,
            "online_in_chats": online_in_chats,
            "public_chat_users": public_chat_users,
            "user": self.user
        }

        html = await sync_to_async(render_to_string)(
            "a_rtchat/partials/online_status.html",
            context
        )

        payload = {
            "type": "online_status",
            "html": html
        }

        await self.send(text_data=json.dumps(payload))
