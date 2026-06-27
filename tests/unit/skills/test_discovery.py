"""Unit tests for ``bundle_dir`` assignment in skill discovery.

``bundle_dir`` must be set only for folder-form skills (``<name>/SKILL.md``),
whose directory is private to that skill. Flat-form skills (``<name>.md``)
share a root with other skills, so surfacing siblings would leak unrelated
files — they must get ``bundle_dir=None``.
"""

from kohakuterrarium.skills.discovery import load_skill_from_path


class TestBundleDirDiscovery:
    def test_folder_form_sets_bundle_dir(self, tmp_path):
        sk = tmp_path / "writer"
        sk.mkdir()
        (sk / "SKILL.md").write_text(
            "---\nname: writer\ndescription: w\nallowed-tools: bash, write\n---\nbody"
        )
        skill = load_skill_from_path(
            sk / "SKILL.md", origin="user", default_name="writer"
        )
        assert skill is not None
        assert skill.bundle_dir == sk
        # allowed-tools frontmatter is parsed into the list form.
        assert skill.allowed_tools == ["bash", "write"]

    def test_flat_form_bundle_dir_none(self, tmp_path):
        flat = tmp_path / "flat.md"
        flat.write_text("---\nname: flat\ndescription: f\n---\nbody")
        skill = load_skill_from_path(flat, origin="user", default_name="flat")
        assert skill is not None
        # base_dir is the shared root; bundle_dir must be None so we never
        # list a sibling skill's files as this skill's resources.
        assert skill.base_dir == tmp_path
        assert skill.bundle_dir is None
