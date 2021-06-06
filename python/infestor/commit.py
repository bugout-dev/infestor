import os
from typing import List

import pygit2


def commit_files(
    repository: str,
    ref: str,
    filepaths: List[str],
    message: str,
    author: str = "Infestor",
    email: str = "infestor@bugout.dev",
) -> str:
    """
    Adds the given files to the repo index and makes a commit.

    Pygit2 commit recipe: https://gist.github.com/lig/dc1ede7e09488a62116fe90aa31617d9
    """
    signature = pygit2.Signature(author, email)
    repo = pygit2.Repository(path=repository)
    for filepath in filepaths:
        repo.index.add(filepath)
    tree = repo.index.write_tree()
    parents = []
    try:
        parent, _ = repo.resolve_refish(refish=repo.head.name)
        parents.append(parent.oid)
    except Exception:
        pass
    commit_oid = repo.create_commit(
        ref,
        signature,
        signature,
        message,
        tree,
        parents,
    )
    return commit_oid
