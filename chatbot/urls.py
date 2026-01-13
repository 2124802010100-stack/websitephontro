from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/history/', views.get_chat_history, name='chat_history'),
    path('widget/', views.chatbot_widget, name='chatbot_widget'),
]
