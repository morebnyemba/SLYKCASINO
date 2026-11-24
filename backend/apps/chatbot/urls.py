from django.urls import path

from . import views

urlpatterns = [
    path('chatbot/whatsapp/webhook/', views.whatsapp_webhook, name='chatbot-whatsapp-webhook'),
    path('chatbot/me/', views.MyChatLinkView.as_view(), name='chatbot-me'),
    path('chatbot/me/link-code/', views.LinkCodeView.as_view(), name='chatbot-link-code'),
    path('chatbot/me/pin/', views.ChatPinView.as_view(), name='chatbot-pin'),
    path('chatbot/me/limit/', views.ChatLimitView.as_view(), name='chatbot-limit'),
    path('admin/chatbot/', views.AdminChatbotView.as_view(), name='chatbot-admin'),
    path('admin/chatbot/test/', views.AdminChatbotTestView.as_view(), name='chatbot-admin-test'),
    path('admin/chatbot/numbers/', views.AdminChatbotNumbersView.as_view(), name='chatbot-admin-numbers'),
    path('admin/chatbot/profile/', views.AdminChatbotProfileView.as_view(), name='chatbot-admin-profile'),
    path('admin/chatbot/profile/photo/', views.AdminChatbotProfilePhotoView.as_view(), name='chatbot-admin-profile-photo'),
    path('admin/chatbot/register/', views.AdminChatbotRegisterView.as_view(), name='chatbot-admin-register'),
    path('admin/chatbot/inbox/', views.AdminInboxView.as_view(), name='chatbot-inbox'),
    path('admin/chatbot/inbox/<str:address>/resolve/', views.AdminInboxResolveView.as_view(), name='chatbot-thread-resolve'),
    path('admin/chatbot/ai/test/', views.AdminAiTestView.as_view(), name='chatbot-ai-test'),
    path('admin/chatbot/ai/knowledge/', views.AdminAiKnowledgeView.as_view(), name='chatbot-ai-knowledge'),
    path('admin/chatbot/inbox/<str:address>/', views.AdminInboxThreadView.as_view(), name='chatbot-thread'),
    path('admin/chatbot/media/<int:pk>/', views.AdminChatbotMediaView.as_view(), name='chatbot-media'),
    path('admin/chatbot/health/', views.AdminChatbotHealthView.as_view(), name='chatbot-health'),
]
