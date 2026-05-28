from pathlib import Path

from django.db import models


class ProjectPath(models.Model):
    path = models.CharField(max_length=4096, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_run = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["path"]

    def __str__(self):
        return self.path

    @property
    def name(self):
        return Path(self.path).name
