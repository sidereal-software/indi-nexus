# Releasing INDINexus

Three packages ship together and carry the same version number: `indi-nexus` on PyPI,
and `@indi-nexus/client` and `@indi-nexus/react` on npm. Release Please keeps them in
lockstep, so there is never a combination of versions to reason about.

Nothing here belongs on the documentation site. It is for whoever cuts the release.

## How a release happens

Every release after the first comes from a pull request:

1. You merge ordinary work into `main` using Conventional Commits.
2. Release Please keeps one **release PR** open, bumping all three packages, proposing
   the next version, and writing the changelogs from those commit messages.
3. You read the PR and merge it.
4. Merging tags the release and creates the GitHub release, which triggers the publish
   jobs in [`.github/workflows/release.yml`](.github/workflows/release.yml).
5. Both registries authenticate with short-lived OIDC tokens, so no credentials are
   stored anywhere in this repository.

There is no manual step. The commit messages are the release notes, which is why
[DEVELOPMENT.md](DEVELOPMENT.md) asks you to write subjects for the person reading the
changelog rather than the person reviewing the diff.

Each package keeps its own changelog, because Release Please files a commit by the paths
it touched: `CHANGELOG.md` for the Python package, and one in each of
`web/packages/client` and `web/packages/react`. The
[changelog page](https://indi-nexus.sidereal.software/changelog/) on the documentation
site shows all three, and the GitHub release carries them together.

If a release note reads badly after merging, edit the merged PR body and wrap a
replacement in `BEGIN_COMMIT_OVERRIDE` / `END_COMMIT_OVERRIDE`; Release Please picks it up
on its next run. To force a version, put `Release-As: 1.2.3` in a commit body.

## One-time setup

Already done, recorded here because it is invisible until it breaks:

- **GitHub**: the `pypi` and `npm` environments exist, and Settings, Actions, General has
  "Allow GitHub Actions to create and approve pull requests" enabled. Without that last
  one, Release Please creates its branch and then fails to open the PR, which looks like
  a workflow bug rather than a permissions setting.
- **PyPI**: a trusted publisher for this repository, workflow `release.yml`, environment
  `pypi`. PyPI accepts a "pending" publisher before the project exists, which is what
  lets the very first upload be automated.
- **npm**: a trusted publisher on each package, environment `npm`. npm cannot configure
  one for a package that does not exist yet, which is why the first publish is manual.

## The first release

Only relevant once, and only because of that last point. npm has no way to trust a
workflow for a package nobody has published, so 0.1.0 goes up by hand:

```bash
# Build from a clean checkout of the tagged commit.
cd web && pnpm install --frozen-lockfile && pnpm -r build && cd ..
uv build
uvx twine check dist/*

uvx twine upload dist/*

cd web
pnpm --filter @indi-nexus/client pack --pack-destination /tmp/tarballs
pnpm --filter @indi-nexus/react pack --pack-destination /tmp/tarballs
npm publish /tmp/tarballs/indi-nexus-client-0.1.0.tgz   # client first
npm publish /tmp/tarballs/indi-nexus-react-0.1.0.tgz    # react depends on it
```

Publish the client before the react package: the react package declares a dependency on
it at the same version, and npm will reject a package whose dependency does not resolve.

Then add the npm trusted publishers, and every release after this one is the PR flow
above.

## Checks before you tag

`uv build` bundles a panel that is **already built**. When one is missing it tries pnpm,
but that is best-effort: with pnpm unavailable it warns and ships a panel-less wheel
rather than failing. So run `pnpm -r build` first, as the block above does, and then
confirm by eye, because each of these has been wrong at least once:

```bash
uvx twine check dist/*
tar -tzf dist/*.tar.gz | grep -c node_modules          # must be 0
unzip -l dist/*.whl | grep -c 'static/panel/index.html' # must be 1
```

CI checks the last of those on every push, and the interop suite runs nightly against a
real `indiserver`. Neither covers the sdist, which is why it is listed here.

## If something goes wrong

The publish jobs skip a version that is already on the registry, so re-running a failed
release is safe and will not produce a half-published version.

`workflow_dispatch` on the release workflow publishes whatever versions are currently on
`main`, ignoring Release Please. That is the escape hatch for a release that was tagged
but whose upload failed.

A version cannot be re-uploaded to either registry. If a release is wrong, the fix is to
release again with the next patch number, never to delete and re-push the same one.
