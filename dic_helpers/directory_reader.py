import os
import glob
import re


class DirectoryReader:
    def __init__(self, directory_path, filter=None, recursive=False):
        self.directory = directory_path
        self.filter = filter or "*"
        self.recursive = recursive

    def list_files(self):
        g = os.path.join(os.path.join(self.directory, "**"), self.filter)
        return glob.iglob(g, recursive=self.recursive)
