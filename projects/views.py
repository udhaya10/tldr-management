import subprocess
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ProjectPath


def project_list(request):
    projects = ProjectPath.objects.all()
    return render(request, "projects/list.html", {"projects": projects})


def browse_directory(request):
    # dev-only: exposes the server filesystem — do not deploy without auth
    raw = request.GET.get("path", str(Path.home()))
    current = Path(raw).resolve()

    try:
        entries = sorted(
            [e for e in current.iterdir() if e.is_dir() and not e.name.startswith(".")],
            key=lambda e: e.name.lower(),
        )
    except PermissionError:
        entries = []

    parent = current.parent if current != current.parent else None

    return render(request, "projects/browser.html", {
        "current": current,
        "entries": entries,
        "parent": parent,
    })


@require_POST
def add_project(request):
    path = request.POST.get("path", "").strip()
    if path and Path(path).is_dir():
        ProjectPath.objects.get_or_create(path=path)
    return redirect("projects:list")


@require_POST
def remove_project(request, pk):
    get_object_or_404(ProjectPath, pk=pk).delete()
    return redirect("projects:list")


def check_project(request, pk):
    project = get_object_or_404(ProjectPath, pk=pk)
    p = Path(project.path)

    git_ok = subprocess.run(
        ["git", "-C", str(p), "rev-parse", "--git-dir"],
        capture_output=True,
    ).returncode == 0

    tldr_ok = (p / ".tldr").is_dir() or (p / ".tldrignore").is_file()

    return JsonResponse({"git": git_ok, "tldr": tldr_ok})
