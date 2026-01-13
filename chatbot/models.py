from django.db import models
from django.contrib.auth.models import User


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='chatbot_messages')
    session_id = models.CharField(max_length=100)
    message = models.TextField()
    response = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_user_message = models.BooleanField(default=True)

    class Meta:
        ordering = ['timestamp']


class VectorDocument(models.Model):
    """
    Store document embeddings for semantic search.
    Uses pgvector if available, otherwise falls back to JSON storage.
    """
    doc_id = models.CharField(max_length=255, unique=True, db_index=True)
    kind = models.CharField(max_length=20, db_index=True)  # 'md' or 'post'
    title = models.CharField(max_length=500)
    url = models.CharField(max_length=500)
    text_snippet = models.TextField()

    # Vector storage - will use pgvector VectorField if extension is installed
    # Otherwise stored as JSON array in TextField
    embedding_pgvector = models.BinaryField(null=True, blank=True)  # placeholder for pgvector field
    embedding_json = models.TextField(null=True, blank=True)  # fallback JSON array

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', 'doc_id']),
        ]

    def __str__(self):
        return f"{self.kind}:{self.doc_id}"
