from __future__ import annotations
from django.contrib import admin
from chat.models import ChatThread, ChatParticipant, ChatMessage

class ChatParticipantInline(admin.TabularInline):
    model = ChatParticipant
    extra = 0
    fields = ("user", "is_deleted", "is_muted", "last_read_at", "unread_count")
    readonly_fields = ("last_read_at", "unread_count")

@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("public_id", "is_group", "item_set", "last_message_at", "last_message_preview")
    search_fields = ("public_id", "last_message_preview")
    inlines = [ChatParticipantInline]
    readonly_fields = ("public_id", "created_at", "updated_at")
    list_select_related = ("item_set",)
    show_full_result_count = False

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("public_id", "thread", "sender", "sent_at")
    search_fields = ("public_id", "content", "sender__email")
    list_filter = ("sender",)
    readonly_fields = ("public_id", "created_at", "updated_at", "sent_at")
    list_select_related = ("thread", "sender")
    show_full_result_count = False
