import json
import subprocess
from pathlib import Path

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ProjectPath

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


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


def runner_page(request):
    scripts = sorted(SCRIPTS_DIR.glob("*.sh"), key=lambda s: s.name)
    projects = ProjectPath.objects.all()
    return render(request, "projects/runner.html", {
        "scripts": scripts,
        "projects": projects,
    })


def run_script(request):
    script_name = request.GET.get("script", "")
    project_pk = request.GET.get("project", "")

    script_path = (SCRIPTS_DIR / script_name).resolve()
    if not str(script_path).startswith(str(SCRIPTS_DIR)) or not script_path.is_file():
        return StreamingHttpResponse("data: invalid script\n\n", content_type="text/event-stream")

    project = get_object_or_404(ProjectPath, pk=project_pk)

    def stream():
        process = subprocess.Popen(
            ["bash", str(script_path), project.path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in process.stdout:
            yield f"data: {json.dumps(line)}\n\n"
        process.wait()
        yield f"data: {json.dumps({'__exit__': process.returncode})}\n\n"

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
