"""Unit tests for the bundle-manifest helpers in :mod:`kohakuterrarium.skill_docs`.

These pin the progressive-disclosure surface that lets a folder-form skill
reference sibling resources (``template/foo.md``): the framework must list
those files and surface the skill's own directory, otherwise relative
references in ``SKILL.md`` are unresolvable.
"""

from kohakuterrarium.skill_docs import (
    build_skill_manifest,
    render_skill_resources,
)


def _make_bundle(root):
    """Create a folder-form skill bundle under ``root`` and return its dir."""
    sk = root / "writer"
    (sk / "template").mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        "---\nname: writer\n---\nBody. See template/science_fiction.md\n"
    )
    (sk / "template" / "science_fiction.md").write_text("scifi")
    (sk / "template" / "fantasy.md").write_text("fantasy")
    return sk


class TestBuildSkillManifest:
    def test_none_returns_empty(self):
        assert build_skill_manifest(None) == []

    def test_missing_dir_returns_empty(self, tmp_path):
        assert build_skill_manifest(tmp_path / "nope") == []

    def test_lists_nested_files_relative_posix(self, tmp_path):
        sk = _make_bundle(tmp_path)
        manifest = build_skill_manifest(sk)
        assert "template/science_fiction.md" in manifest
        assert "template/fantasy.md" in manifest

    def test_excludes_top_level_skill_md(self, tmp_path):
        sk = _make_bundle(tmp_path)
        # The entrypoint is rendered as the body; it must not double as a
        # "bundled file".
        assert "SKILL.md" not in build_skill_manifest(sk)

    def test_keeps_nested_skill_md(self, tmp_path):
        sk = _make_bundle(tmp_path)
        (sk / "references").mkdir()
        (sk / "references" / "SKILL.md").write_text("nested")
        # Only the *top-level* SKILL.md is the entrypoint; a nested one is a
        # legitimate resource.
        assert "references/SKILL.md" in build_skill_manifest(sk)

    def test_skips_heavy_and_hidden_dirs(self, tmp_path):
        sk = _make_bundle(tmp_path)
        (sk / "__pycache__").mkdir()
        (sk / "__pycache__" / "x.pyc").write_text("x")
        (sk / ".git").mkdir()
        (sk / ".git" / "config").write_text("x")
        manifest = build_skill_manifest(sk)
        assert not any("pycache" in m or ".git" in m for m in manifest)

    def test_is_sorted_deterministically(self, tmp_path):
        sk = _make_bundle(tmp_path)
        manifest = build_skill_manifest(sk)
        assert manifest == sorted(manifest)

    def test_max_files_bounds_output(self, tmp_path):
        sk = tmp_path / "big"
        sk.mkdir()
        (sk / "SKILL.md").write_text("body")
        for i in range(10):
            (sk / f"f{i}.txt").write_text("x")
        assert len(build_skill_manifest(sk, max_files=3)) == 3


class TestRenderSkillResources:
    def test_none_returns_empty_string(self):
        assert render_skill_resources(None) == ""

    def test_empty_bundle_returns_empty_string(self, tmp_path):
        sk = tmp_path / "solo"
        sk.mkdir()
        (sk / "SKILL.md").write_text("body")  # only the entrypoint, no siblings
        assert render_skill_resources(sk) == ""

    def test_block_contains_absolute_dir_and_files(self, tmp_path):
        sk = _make_bundle(tmp_path)
        block = render_skill_resources(sk)
        assert str(sk.resolve()) in block
        assert "template/science_fiction.md" in block
        # Must steer the model to the read tool for on-demand loading.
        assert "read" in block
        assert "Skill resources" in block
