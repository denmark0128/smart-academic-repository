
from django.urls import path, include
from . import views
from rest_framework import routers
from .api import PaperViewSet, SavedPaperViewSet

router = routers.DefaultRouter()
router.register(r'api/papers', PaperViewSet)
router.register(r'api/savedpapers', SavedPaperViewSet)

urlpatterns = [
    path('', views.paper_list, name='paper_list'),
    path('papers/<int:pk>/', views.paper_detail, name='paper_detail'),
    path('papers/<int:pk>/query/', views.paper_query, name='paper_query'),  # new
    path('upload/', views.paper_upload, name='paper_upload'),
    path('profile/', views.profile_page, name='profile_page'),
    path('saved/', views.saved_papers, name='saved_papers'),
    path('extract-metadata/', views.extract_metadata, name='extract_metadata'),
    path('insights/', views.paper_insights, name='paper_insights'),
    path('save/<int:paper_id>/', views.save_paper, name='save_paper'),
    path('unsave/<int:pk>/', views.unsave_paper, name='unsave_paper'),
    path('toast/', views.toast, name='toast'),
    path("upload/tab/", views.upload_tab, name="upload_tab"),
    path("processing/tab/", views.processing_tab, name="processing_tab"),
    path("review/tab/", views.review_tab, name="review_tab"),
    path('', include(router.urls)),
]