
from django.urls import path, include
from .views import views
from .views.partial_views import *
from rest_framework import routers
from .api import PaperViewSet, SavedPaperViewSet

router = routers.DefaultRouter()
router.register(r'api/papers', PaperViewSet)
router.register(r'api/savedpapers', SavedPaperViewSet)

urlpatterns = [
    path("protected-media/<path:path>", views.protected_media, name="protected_media"),
    path('', views.paper_list, name='paper_list'),
    path('papers/<int:pk>/', views.paper_detail, name='paper_detail'),
    path('autocomplete/', views.autocomplete, name='autocomplete'),
    path('upload/', views.paper_upload, name='paper_upload'),
    path('profile/', views.profile_page, name='profile_page'),
    path('saved/', views.saved_papers, name='saved_papers'),
    path('extract-metadata/', views.extract_metadata, name='extract_metadata'),
    path('insights/', views.paper_insights, name='paper_insights'),
    path('save/<int:pk>/', views.save_paper, name='save_paper'),
    path('unsave/<int:pk>/', views.unsave_paper, name='unsave_paper'),
    path('saveList/<int:pk>/', views.save_paper_list, name='save_paper_list'),
    path('unsaveList/<int:pk>/', views.unsave_paper_list, name='unsave_paper_list'),
    path('toast/', views.toast, name='toast'),
    path("upload/tab/", views.upload_tab, name="upload_tab"),
    path("processing/tab/", views.processing_tab, name="processing_tab"),
    path("review/tab/", views.review_tab, name="review_tab"),
    path('', include(router.urls)),
    path('partials/uploaded-papers/', uploaded_papers_partial, name='uploaded_papers_partial'),
    path('partials/paper-list/', paper_list_partial, name='paper_list_partial'),
    path('partials/saved-papers/', saved_papers_partial, name='saved_papers_partial'),
    path('paper/<int:pk>/partials/', paper_detail_partials, name='paper_detail_partials'),
    path("footer/", footer_partial, name="footer_partial"),
    path("rag-chat/", views.rag_chat_view, name="rag_chat"),
    path('paper-review-list/', paper_review_list, name='paper_review_list'),
    path('partials/review/', review_papers_partial, name='review_papers_partials'),
    path('paper/<int:pk>/query/', views.paper_query, name='paper_query'),
    path('paper/<int:pk>/get-answer/', views.get_answer, name='get_answer'),
    path('insights/chart/<str:chart_type>/', insights_partial, name='insights_partial'), 
]

