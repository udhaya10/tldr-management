from django.urls import include, path

urlpatterns = [
    path("projects/", include("projects.urls")),
]
