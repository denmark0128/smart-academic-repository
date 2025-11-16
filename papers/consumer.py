import json
import uuid
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string
from utils.single_paper_rag import query_rag  # your RAG pipeline

class RAGChatConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        self.messages = []

    def receive(self, text_data):
        data = json.loads(text_data)
        query = data.get("message", "").strip()
        if not query:
            return

        # render user message
        user_html = render_to_string("papers/user_message.html", {"message_text": query})
        self.send(text_data=user_html)

        # placeholder for system message
        message_id = uuid.uuid4().hex
        div_id = f"response-{message_id}"
        placeholder_html = render_to_string("papers/system_message.html", {"contents_div_id": div_id})
        self.send(text_data=placeholder_html)

        # stream RAG response
        for chunk in query_rag(query):
            self.send(text_data=f'<div hx-swap-oob="beforeend:#{div_id}">{chunk}</div>')
