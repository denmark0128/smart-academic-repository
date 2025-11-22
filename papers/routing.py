from django.urls import path
from .consumer import RAGChatConsumer

websocket_urlpatterns = [
    path("ws/rag-chat/", RAGChatConsumer.as_asgi()),
]
