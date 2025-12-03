from django.urls import path
from .views import (chat_view,
    get_or_create_chatroom,
    create_groupchat,
    chatroom_edit_view,
    chatroom_delete_view,
    chatroom_leave_view,
    chat_file_upload,)

urlpatterns = [
    # Home Chat page
    path('', chat_view, name="home"),

    # Group Chat Create
    path('chat/new_groupchat/', create_groupchat, name="new-groupchat"),

    # Chatroom related pages  
    path('chat/room/<str:chatroom_name>/', chat_view, name="chatroom"),
    path('chat/edit/<str:chatroom_name>/', chatroom_edit_view, name="edit-chatroom"),
    path('chat/delete/<str:chatroom_name>/', chatroom_delete_view, name="chatroom-delete"),
    path('chat/leave/<str:chatroom_name>/', chatroom_leave_view, name="chatroom-leave"),
    path('chat/fileupload/<str:chatroom_name>/', chat_file_upload, name="chat-file-upload"),

    # Start chat with a user (must be last to avoid URL clashes)
    path('chat/<str:username>/', get_or_create_chatroom, name="start-chat"),
]