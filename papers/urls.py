from django.urls import path
from . import views 

urlpatterns = [
    path('', views.paper_list, name='paper_list'),
    path('papers/<int:pk>/', views.paper_detail, name='paper_detail'),
    path('upload/', views.paper_upload, name='paper_upload'),
]