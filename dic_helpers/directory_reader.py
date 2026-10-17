"""Listing the files of a directory, optionally including its subdirectories."""
import fnmatch
import os
from pathlib import Path
from typing import Iterable, List, Set, Tuple, Union


class DirectoryReader:
    """
    Lists the files of a directory whose names match one of the given patterns.
    """

    def __init__(self, directory: Union[str, os.PathLike], patterns: Union[str, Iterable[str]] = ("*",),
                 recursive: bool = False, include_hidden: bool = False, follow_symlinks: bool = False) -> None:
        """
        Initialize the DirectoryReader. The directory is only read by list_files().

        :param directory: The directory to read.
        :type directory: Union[str, os.PathLike]
        :param patterns: Shell-style patterns (fnmatch: *, ?, [seq]) matched case-sensitively against the file names,
            e.g. ("*.json", "*.ndjson"). A single pattern can be given as a string. A file is listed if it matches any
            pattern.
        :type patterns: Union[str, Iterable[str]]
        :param recursive: Also list the files of all subdirectories.
        :type recursive: bool
        :param include_hidden: Also list hidden files (names starting with '.') and read hidden subdirectories.
        :type include_hidden: bool
        :param follow_symlinks: Also read subdirectories that are symbolic links. Every directory is read once at most,
            so symlink loops end. Symbolic links to files are always listed.
        :type follow_symlinks: bool
        """
        self.directory = Path(directory)
        self.patterns: Tuple[str, ...] = (patterns,) if isinstance(patterns, str) else tuple(patterns)
        self.recursive = recursive
        self.include_hidden = include_hidden
        self.follow_symlinks = follow_symlinks

    def list_files(self) -> List[Path]:
        """
        List the matching files.

        :return: The paths of the matching regular files, sorted. Each path starts with the directory as given.
        :rtype: List[Path]
        :raises FileNotFoundError: If the directory doesn't exist.
        :raises NotADirectoryError: If the path is not a directory.
        :raises PermissionError: If the directory or one of the subdirectories to read can't be read.
        """
        if not self.directory.exists():
            raise FileNotFoundError(f"Directory not found: {self.directory}")
        if not self.directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.directory}")
        files: List[Path] = []
        self._read(self.directory, files, visited=set())
        return sorted(files)

    def _read(self, directory: Path, files: List[Path], visited: Set[Tuple[int, int]]) -> None:
        """
        Add the matching files of a directory to files, and read its subdirectories if recursive.

        :param directory: The directory to read.
        :type directory: Path
        :param files: The list the matching files are added to.
        :type files: List[Path]
        :param visited: Device and inode of the directories read so far; directories in it are not read again.
        :type visited: Set[Tuple[int, int]]
        """
        status = directory.stat()
        visited.add((status.st_dev, status.st_ino))
        with os.scandir(directory) as entries:
            for entry in entries:
                if not self.include_hidden and entry.name.startswith("."):
                    continue
                # is_file() follows symbolic links: links to files are listed, broken links are not
                if entry.is_file():
                    if any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in self.patterns):
                        files.append(Path(entry.path))
                elif self.recursive and entry.is_dir(follow_symlinks=self.follow_symlinks):
                    status = entry.stat()
                    if (status.st_dev, status.st_ino) not in visited:
                        self._read(Path(entry.path), files, visited)
