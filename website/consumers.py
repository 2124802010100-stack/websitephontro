import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import RentalPost, ChatThread, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.room_group_name = f'chat_thread_{self.thread_id}'

        # Accept connection
        await self.accept()
        print(f"WebSocket connected for thread {self.thread_id}")

        # Join group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'chat.message':
            content = text_data_json.get('content')
            user = self.scope['user']

            print(f"Received message: {content} from user: {user}")

            if content and user.is_authenticated:
                await self.save_message(content, user)

            # gửi lại cho group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'content': content,
                        'sender': user.username if user.is_authenticated else 'Anonymous',
                        'sender_id': user.id if user.is_authenticated else 0,
                        'timestamp': text_data_json.get('timestamp', ''),
                    }
                }
            )

    async def chat_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps({
            'type': 'chat.message',
            'message': message
        }))

    @database_sync_to_async
    def save_message(self, content, user):
       thread = ChatThread.objects.get(id=self.thread_id)
       # Chỉ cho owner hoặc guest gửi
       if user != thread.owner and user != thread.guest:
           return None
       # Khi có tin nhắn mới, tự động bỏ ẩn cho cả hai phía
       changed_fields = []
       if thread.hidden_for_owner:
           thread.hidden_for_owner = False
           thread.hidden_for_owner_at = None
           changed_fields += ['hidden_for_owner', 'hidden_for_owner_at']
       if thread.hidden_for_guest:
           thread.hidden_for_guest = False
           thread.hidden_for_guest_at = None
           changed_fields += ['hidden_for_guest', 'hidden_for_guest_at']
       if changed_fields:
           thread.save(update_fields=changed_fields)

       ChatMessage.objects.create(
           thread=thread,
           sender=user,
           content=content
       )
       return thread

