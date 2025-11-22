# staff/urls.py
from django.urls import path
from . import views
from .partial_views import *


urlpatterns = [
    path("", views.staff_dashboard, name="staff_dashboard"),
    path("pending/", views.staff_pending_papers, name="staff_pending"),
    path("registered/", views.staff_registered_papers, name="staff_registered"),
    path("review/<int:pk>/", views.review_paper, name="staff_review_paper"),
    path("approve/<int:pk>/", views.approve_paper, name="staff_approve_paper"),
    path('papers/table/', staff_table_partial, name='staff_table_partial'),  # HTMX partial
    path('dashboard/stats/', staff_stats_partial, name='staff_stats_partial'),
    path('dashboard/', staff_dashboard_partial, name='staff_dashboard_partial'),
    path('staff/tags/', staff_tags_partial, name='staff_tags_partial'),
    path('staff/papers', staff_papers_partial, name='staff_papers_partial'),
    path('staff/papers/table', staff_papers_table_partial, name='staff_papers_table_partial'),
    path('staff/papers/<int:paper_id>/regenerate-tags/', staff_paper_regenerate_tags, name='staff_paper_regenerate_tags'),
    path('staff/tags/table/', staff_tags_table, name='staff_tags_table'),
    path('staff/tags/create/', staff_tags_create, name='staff_tags_create'),
    path('staff/tags/<int:tag_id>/update/', staff_tags_update, name='staff_tags_update'),
    path('staff/tags/<int:tag_id>/toggle/', staff_tags_toggle, name='staff_tags_toggle'),
    path('staff/tags/<int:tag_id>/delete/', staff_tags_delete, name='staff_tags_delete'),
    path('staff/tags/<int:tag_id>/generate-embedding/', staff_tags_generate_embedding, name='staff_tags_generate_embedding'),
    path('settings/search/', search_settings_view, name='search_settings'),
    path('settings/llama/', llama_settings_view, name='llama_settings'),

]   


