from django.urls import path

from . import views

urlpatterns = [
    path('chatbot/whatsapp/webhook/', views.whatsapp_webhook, name='chatbot-whatsapp-webhook'),
    path('chatbot/me/', views.MyChatLinkView.as_view(), name='chatbot-me'),
    path('chatbot/me/link-code/', views.LinkCodeView.as_view(), name='chatbot-link-code'),
    path('chatbot/me/pin/', views.ChatPinView.as_view(), name='chatbot-pin'),
    path('chatbot/me/limit/', views.ChatLimitView.as_view(), name='chatbot-limit'),
    path('admin/chatbot/', views.AdminChatbotView.as_view(), name='chatbot-admin'),
]
