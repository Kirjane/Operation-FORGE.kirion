"""Descriptor-confined fixed fixture mutation, not a native sandbox."""
import os
import stat
from contextlib import contextmanager


class FenceDenied(ValueError):
    pass


def supported():
    return (os.name == "posix" and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NONBLOCK")
            and {os.open, os.stat} <= os.supports_dir_fd
            and os.stat in os.supports_follow_symlinks)


def identity(st):
    return (st.st_dev, st.st_ino)


@contextmanager
def fixed_file(root, root_identity, directory_identity, file_identity, before, *, directory='docs', filename='owned.txt'):
    if (directory, filename) not in {('docs', 'owned.txt'), ('ui', 'owned.md')}:
        raise FenceDenied('FIXTURE_PATH_NOT_SUPPORTED')
    if not supported():
        raise FenceDenied("DESCRIPTOR_CONFINEMENT_UNAVAILABLE")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    try:
        docs_fd = os.open(directory, flags, dir_fd=root_fd)
        try:
            fd = os.open(filename, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=docs_fd)
            try:
                def verify():
                    root_st = os.stat(root, follow_symlinks=False)
                    docs_st = os.stat(directory, dir_fd=root_fd, follow_symlinks=False)
                    named = os.stat(filename, dir_fd=docs_fd, follow_symlinks=False)
                    opened = os.fstat(fd)
                    if (not stat.S_ISDIR(root_st.st_mode) or
                            not stat.S_ISDIR(docs_st.st_mode) or
                            identity(root_st) != root_identity or
                            identity(os.fstat(root_fd)) != root_identity or
                            identity(docs_st) != directory_identity or
                            identity(os.fstat(docs_fd)) != directory_identity or
                            not stat.S_ISREG(opened.st_mode) or
                            not stat.S_ISREG(named.st_mode) or
                            identity(named) != file_identity or
                            identity(opened) != file_identity or
                            opened.st_nlink != 1 or named.st_nlink != 1):
                        raise FenceDenied("FIXTURE_DESCRIPTOR_IDENTITY_CHANGED")

                def read_expected(expected):
                    verify()
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.read(fd, len(expected) + 1) != expected:
                        raise FenceDenied("FIXTURE_DESCRIPTOR_BYTES_CHANGED")

                read_expected(before)

                def replace(after):
                    read_expected(before)
                    os.lseek(fd, 0, os.SEEK_SET)
                    remaining = memoryview(after)
                    while remaining:
                        count = os.write(fd, remaining)
                        if count <= 0:
                            raise OSError("short fixture write")
                        remaining = remaining[count:]
                    os.ftruncate(fd, len(after))
                    os.fsync(fd)
                    read_expected(after)

                yield replace
            finally:
                os.close(fd)
        finally:
            os.close(docs_fd)
    finally:
        os.close(root_fd)
