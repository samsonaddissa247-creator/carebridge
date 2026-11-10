from django.urls import path

from . import views

urlpatterns = [
    path("", views.chat_page, name="assistant_chat"),
    path("message/", views.chat_message, name="assistant_message"),
]
