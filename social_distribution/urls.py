from django.urls import path
from . import views

app_name = "social_distribution"
urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    path("api/entries/", views.get_entries, name="get_entries"),
]