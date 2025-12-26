from rest_framework import serializers
from chat.models import ChatThread, ChatMessage, ChatParticipant
from identity.models import User
from listings.serializers import ItemSetPublicResponse

class UserMini(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("public_id", "first_name", "last_name", "user_image", "display_name")

    def get_display_name(self, obj: User) -> str:
        name = f"{(obj.first_name or '').strip()} {(obj.last_name or '').strip()}".strip()
        if name:
            return name
        try:
            return obj.email.split("@", 1)[0] if obj.email else "Użytkownik"
        except Exception:
            return obj.email or "Użytkownik"


class ChatParticipantResponse(serializers.ModelSerializer):
    user = UserMini()
    class Meta:
        model = ChatParticipant
        fields = ("public_id", "user", "is_deleted", "is_muted", "last_read_at", "unread_count")


class ChatThreadResponse(serializers.ModelSerializer):
    participants = ChatParticipantResponse(many=True)
    item = ItemSetPublicResponse(source="item_set")
    thread_kind = serializers.SerializerMethodField()  # < rodzaj wątku

    class Meta:
        model = ChatThread
        fields = (
            "public_id", "is_group", "item",
            "last_message_preview", "last_message_at",
            "participants", "created_at", "updated_at",
            "thread_kind",
        )

    def get_thread_kind(self, obj: ChatThread) -> str:
        """
        Jedna z wartości: 'my_user' | 'users_other' | 'sellers' | 'dm'
        """
        if not obj.item_set_id:
            return "dm"
        item = obj.item_set
        if item.added_by == "STAFF":
            return "sellers"
        req = self.context.get("request") if self.context else None
        current_user_id = getattr(getattr(req, "user", None), "id", None)
        if current_user_id and item.owner_user_id == current_user_id:
            return "my_user"
        return "users_other"


class ChatMessageResponse(serializers.ModelSerializer):
    sender = UserMini()

    class Meta:
        model = ChatMessage
        fields = ("public_id", "sender", "content", "sent_at")

# --- requests ---

class StartDMRequest(serializers.Serializer):
    other_user_public_id = serializers.CharField(required=False, allow_blank=True)
    item_public_id = serializers.CharField(required=False, allow_blank=True)


class SendMessageRequest(serializers.Serializer):
    content = serializers.CharField(max_length=5000)


class ListMessagesRequest(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=200, required=False, default=50)
    before = serializers.CharField(required=False, allow_blank=True)
