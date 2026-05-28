from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("browse/", views.browse_directory, name="browse"),
    path("add/", views.add_project, name="add"),
    path("<int:pk>/remove/", views.remove_project, name="remove"),
    path("<int:pk>/check/", views.check_project, name="check"),
    path("runner/", views.runner_page, name="runner"),
    path("run/", views.run_script, name="run"),
]
