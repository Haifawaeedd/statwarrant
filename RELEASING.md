# Releasing statwarrant

A checklist for the maintainer. Nothing is published automatically.

## Before the release

1. Merge the release pull request into `main` only when the **tests** workflow is green on
   all jobs (Linux matrix, macOS, Windows, oldest dependencies).
2. Ask one reviewer to read the final commit (read-only) and record any finding in
   `KNOWN_ISSUES.md` before tagging. One person edits at a time.
3. Check that `pyproject.toml`, `src/statwarrant/_version.py` and `CITATION.cff` carry the
   same version, and that `CHANGELOG.md` has its section.

## Release

4. Tag the merge commit on `main` and push the tag:
   `git tag -a v0.5.0 -m "statwarrant 0.5.0" && git push origin v0.5.0`.
5. Create a GitHub release from the tag, with the CHANGELOG section as notes, marked as a
   pre-release while the package is experimental.
6. Check that the Colab link in the README opens and that its first cells install the tag.

## Optional: PyPI

7. Configure the `testpypi` and `pypi` environments (required reviewer for `pypi`,
   deployment restricted to `v*` tags) and the pending trusted publishers, as described at
   the top of `.github/workflows/release.yml`.
8. Run the **release** workflow by hand from the tag with target `testpypi`, install from
   TestPyPI in a clean environment and run the quick start; then run it with target `pypi`.
9. Update the README install line to `pip install statwarrant==0.5.0`.

## Repository settings (once)

* Enable Discussions (the issue forms link to them) and private vulnerability reporting
  (see `SECURITY.md`).
* Optionally connect Zenodo to mint a DOI for each release, and add it to `CITATION.cff`.
