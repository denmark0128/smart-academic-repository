from django.urls import path
from . import views 

urlpatterns = [
    path('', views.paper_list, name='paper_list'),
    path('papers/<int:pk>/', views.paper_detail, name='paper_detail'),
    path('upload/', views.paper_upload, name='paper_upload'),
    path('profile/', views.profile_page, name='profile_page'),
    path('papers/<int:pk>/save/', views.save_paper, name='save_paper'),
    path('saved/', views.saved_papers_view, name='saved_papers'),
]