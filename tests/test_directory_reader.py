import os
from pathlib import Path

import pytest

from dic_helpers.directory_reader import DirectoryReader

# These tests build small directory trees in tmp_path and check which files DirectoryReader lists
# (README "Directory reader").


# Without recursive, only the files directly in the directory are listed, sorted, and no directories
def test_files_of_the_directory(tmp_path):
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.json").write_text("{}")

    files = DirectoryReader(tmp_path).list_files()

    assert files == [tmp_path / "a.json", tmp_path / "b.json"]


# With recursive, the files of all subdirectories are listed too, sorted by path
def test_recursive(tmp_path):
    (tmp_path / "z.json").write_text("{}")
    (tmp_path / "sub" / "deeper").mkdir(parents=True)
    (tmp_path / "sub" / "c.json").write_text("{}")
    (tmp_path / "sub" / "deeper" / "d.json").write_text("{}")

    files = DirectoryReader(tmp_path, recursive=True).list_files()

    assert files == [tmp_path / "sub" / "c.json", tmp_path / "sub" / "deeper" / "d.json", tmp_path / "z.json"]


# The paths are Path objects that start with the directory as given, here a relative one
def test_paths_start_with_the_given_directory(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.json").write_text("{}")
    monkeypatch.chdir(tmp_path)

    files = DirectoryReader("data").list_files()

    assert files == [Path("data/a.json")]


# A single pattern can be given as a string; directories matching it are not listed
def test_single_pattern(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.ndjson").write_text("{}")
    (tmp_path / "folder.json").mkdir()

    files = DirectoryReader(tmp_path, patterns="*.json").list_files()

    assert files == [tmp_path / "a.json"]


# With several patterns, a file is listed if it matches any of them
def test_several_patterns(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.ndjson").write_text("{}")
    (tmp_path / "c.txt").write_text("")

    files = DirectoryReader(tmp_path, patterns=["*.json", "*.ndjson"]).list_files()

    assert files == [tmp_path / "a.json", tmp_path / "b.ndjson"]


# Patterns are matched case-sensitively, on every operating system
def test_patterns_are_case_sensitive(tmp_path):
    (tmp_path / "upper.JSON").write_text("{}")
    (tmp_path / "lower.json").write_text("{}")

    files = DirectoryReader(tmp_path, patterns="*.json").list_files()

    assert files == [tmp_path / "lower.json"]


# Patterns in subdirectories are matched against the file names, not the paths
def test_patterns_match_file_names_in_subdirectories(tmp_path):
    (tmp_path / "export.json").mkdir()
    (tmp_path / "export.json" / "patient.txt").write_text("")
    (tmp_path / "export.json" / "consent.json").write_text("{}")

    files = DirectoryReader(tmp_path, patterns="*.json", recursive=True).list_files()

    assert files == [tmp_path / "export.json" / "consent.json"]


# Characters with a meaning in patterns ([, ], *, ?) in the directory's own name don't matter
def test_special_characters_in_the_directory_name(tmp_path):
    directory = tmp_path / "export [2026] *?"
    directory.mkdir()
    (directory / "a.json").write_text("{}")

    files = DirectoryReader(directory).list_files()

    assert files == [directory / "a.json"]


# Hidden files are not listed, hidden directories are not read
def test_hidden_files_and_directories_are_skipped(tmp_path):
    (tmp_path / "visible.json").write_text("{}")
    (tmp_path / ".hidden.json").write_text("{}")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.json").write_text("{}")

    files = DirectoryReader(tmp_path, recursive=True).list_files()

    assert files == [tmp_path / "visible.json"]


# With include_hidden, hidden files are listed and hidden directories are read
def test_include_hidden(tmp_path):
    (tmp_path / "visible.json").write_text("{}")
    (tmp_path / ".hidden.json").write_text("{}")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.json").write_text("{}")

    files = DirectoryReader(tmp_path, recursive=True, include_hidden=True).list_files()

    assert files == [tmp_path / ".git" / "config.json", tmp_path / ".hidden.json", tmp_path / "visible.json"]


# Symbolic links to files are listed; broken links are not
def test_symbolic_links_to_files(tmp_path):
    (tmp_path / "target.json").write_text("{}")
    (tmp_path / "link.json").symlink_to(tmp_path / "target.json")
    (tmp_path / "broken.json").symlink_to(tmp_path / "missing.json")

    files = DirectoryReader(tmp_path).list_files()

    assert files == [tmp_path / "link.json", tmp_path / "target.json"]


# Symbolic links to directories are not read by default ...
def test_symbolic_links_to_directories_are_not_followed(tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "a.json").write_text("{}")
    (tmp_path / "read").mkdir()
    (tmp_path / "read" / "linked").symlink_to(tmp_path / "elsewhere")

    files = DirectoryReader(tmp_path / "read", recursive=True).list_files()

    assert files == []


# ... but with follow_symlinks
def test_follow_symlinks(tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "a.json").write_text("{}")
    (tmp_path / "read").mkdir()
    (tmp_path / "read" / "linked").symlink_to(tmp_path / "elsewhere")

    files = DirectoryReader(tmp_path / "read", recursive=True, follow_symlinks=True).list_files()

    assert files == [tmp_path / "read" / "linked" / "a.json"]


# With follow_symlinks, a link back to a parent directory doesn't loop: every directory is read once
def test_symlink_loop(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.json").write_text("{}")
    (tmp_path / "sub" / "back").symlink_to(tmp_path)

    files = DirectoryReader(tmp_path, recursive=True, follow_symlinks=True).list_files()

    assert files == [tmp_path / "sub" / "a.json"]


# An empty directory gives an empty list
def test_empty_directory(tmp_path):
    assert DirectoryReader(tmp_path, recursive=True).list_files() == []


# A missing directory is an error, so an empty list always means an empty directory
def test_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="Directory not found: .*missing"):
        DirectoryReader(tmp_path / "missing").list_files()


# A file instead of a directory is an error
def test_file_instead_of_a_directory(tmp_path):
    (tmp_path / "a.json").write_text("{}")

    with pytest.raises(NotADirectoryError, match="Not a directory: .*a.json"):
        DirectoryReader(tmp_path / "a.json").list_files()


# A subdirectory that can't be read is an error, not silently skipped
@pytest.mark.skipif(os.geteuid() == 0, reason="root can read every directory")
def test_unreadable_subdirectory(tmp_path):
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked").chmod(0)
    try:
        with pytest.raises(PermissionError):
            DirectoryReader(tmp_path, recursive=True).list_files()
    finally:
        (tmp_path / "locked").chmod(0o755)
