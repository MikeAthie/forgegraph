from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_release_images_are_tagged_with_immutable_commit_sha() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "sha-${{ github.event.workflow_run.head_sha }}" in workflow
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert "Verify immutable release checkout" in workflow
    assert "git diff --quiet" in workflow
    assert "git diff --cached --quiet" in workflow
    assert "git status --porcelain" in workflow


def test_release_workflow_does_not_publish_branch_image_tags() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    forbidden_fragments = [
        "branch_tag",
        ":${{ github.event.workflow_run.head_branch }}",
        ":${{ needs.prepare.outputs.branch_tag }}",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in workflow


def test_release_workflow_uses_resolvable_trivy_action_tag() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "uses: aquasecurity/trivy-action@v0.28.0" in workflow
    assert "uses: aquasecurity/trivy-action@0.28.0" not in workflow
