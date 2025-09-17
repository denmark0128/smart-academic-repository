# staff/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.staff_dashboard, name="staff_dashboard"),
    path("pending/", views.staff_pending_papers, name="staff_pending"),
    path("registered/", views.staff_registered_papers, name="staff_registered"),
    path("review/<int:pk>/", views.review_paper, name="staff_review_paper"),
    path("approve/<int:pk>/", views.approve_paper, name="staff_approve_paper"),
]

