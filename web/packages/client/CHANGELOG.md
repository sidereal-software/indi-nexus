# Changelog

## [0.3.0](https://github.com/sidereal-software/indikit/compare/client-v0.2.0...client-v0.3.0) (2026-08-20)


### ⚠ BREAKING CHANGES

* the distribution, the import package and the CLI are all `indikit`; the environment prefix is `INDIKIT_`; the npm packages are `@indikit/client` and `@indikit/react`; and the driver property `NEXUS_CONFIG_PERSISTED` is now `INDIKIT_CONFIG_PERSISTED`. Nothing was ever published under the old names, so no upgrade path is provided.
* **a11y:** `AlertAnnouncer` is renamed to `StatusAnnouncer`. It now announces three things and only one of them is an alert: a vector entering Alert, an operator-initiated write reaching a settled state, and connection loss or recovery. The new name matches the `role="status"` it renders.

### Added

* **client:** add onWrite so a consumer can tell its writes from telemetry ([0c91fab](https://github.com/sidereal-software/indikit/commit/0c91fab9664111ca7a5328d83895f110eb544a20))
* **web:** version the browser JSON contract with a hello frame ([6a4333a](https://github.com/sidereal-software/indikit/commit/6a4333ac00400652ca3f65649d35909a46802548))


### Fixed

* **a11y:** correct contrast, targets and motion from theme.css ([d37ca55](https://github.com/sidereal-software/indikit/commit/d37ca558033ede615659a7d7db482d1ca48451df))
* **client:** fall back to the element name when a label is blank ([a887fbf](https://github.com/sidereal-software/indikit/commit/a887fbfdcd29bdd94c9e0e283d940792f199193d))
* **client:** mirror the new protocol rules in the browser store ([398ab0b](https://github.com/sidereal-software/indikit/commit/398ab0b422d333e34059b5a73a43afcdad3fb160))
* **client:** stop a reconnect timer orphaning a live socket ([cfa0311](https://github.com/sidereal-software/indikit/commit/cfa0311555ae28a784f80f6e9c5ef6b367900cdf))
* **driver:** remove a property when it is deleted, as libindi does ([c5d3292](https://github.com/sidereal-software/indikit/commit/c5d32921f63338722e738820c6344593f0e7e4f9))
* **protocol:** emit standard base64 for a BLOB, not the URL-safe alphabet ([064d1c7](https://github.com/sidereal-software/indikit/commit/064d1c72cd342d7adacb246099c44eaa789c2054))


### Documentation

* reconcile every document with the three new surfaces ([9c5c13c](https://github.com/sidereal-software/indikit/commit/9c5c13c050c4d5b0270acf4ae37774d58fb3a690))
* reconcile the guides, the register and the conventions ([bdb2571](https://github.com/sidereal-software/indikit/commit/bdb2571bec68919c8b58f40096b4e7b7a41bb928))
* rewrite the guides and READMEs in a plainer tone ([d6ad6cd](https://github.com/sidereal-software/indikit/commit/d6ad6cdd7e3fad2146ae609a31c36d7c9caee04e))


### Changed

* rename the project to INDIkit ([1b5cfd6](https://github.com/sidereal-software/indikit/commit/1b5cfd629a17ffd08c92866df6604ddf79b95c73))

## [0.2.0](https://github.com/sidereal-software/indi-nexus/compare/client-v0.1.0...client-v0.2.0) (2026-08-15)


### Added

* **web:** add @indi-nexus/client transport and property store ([6c77924](https://github.com/sidereal-software/indi-nexus/commit/6c779246a67615d3edd2bc5b5f57e11dcd3f0c0b))
* **web:** live current-value readouts on writable elements ([c631c1e](https://github.com/sidereal-software/indi-nexus/commit/c631c1e0468239fed416255fb586fcc2efd0f8c3))


### Fixed

* **client:** ignore a socket that has already been superseded ([7b4d0e2](https://github.com/sidereal-software/indi-nexus/commit/7b4d0e283f134032c7500a1eb10cde5640b64b2a))
* **client:** keep a property's state when a set does not carry one ([dfa9a46](https://github.com/sidereal-software/indi-nexus/commit/dfa9a4652099f0863642966a1c4f13b3bb12357d))
* **client:** key BLOB policies on a pair, and drop non-object frames ([ff2d87e](https://github.com/sidereal-software/indi-nexus/commit/ff2d87e5ec91bfe3ad5f7957f76723407f6a80b7))
* **client:** render numbers the way the wire renders them ([9903f21](https://github.com/sidereal-software/indi-nexus/commit/9903f216257752a333f67bdf89d9d3c13d5c6237))
* **web:** buffer INDI messages and replay them to late-joining viewers ([93c258e](https://github.com/sidereal-software/indi-nexus/commit/93c258e1550567401dd1ec4b56f652635b05661a))


### Packaging

* automate PyPI and npm releases ([097a3b9](https://github.com/sidereal-software/indi-nexus/commit/097a3b9dfdea435e1063f845baac5e3eecf303f1))
* let Release Please own the changelog and drop towncrier ([8a37c37](https://github.com/sidereal-software/indi-nexus/commit/8a37c37ffef52b614301593c51575ebe2693c2ff))


### Documentation

* fix the claims an audit found were no longer true ([65c8cc9](https://github.com/sidereal-software/indi-nexus/commit/65c8cc9ec053a5a61a780456f05af1013a7fd0f4))
* **web:** add readmes and licences to the published npm packages ([169e304](https://github.com/sidereal-software/indi-nexus/commit/169e304853614769b349644bc7e4a065a5e460ac))

## @indi-nexus/client changelog

Releases of the framework-agnostic TypeScript client. It ships at the same version as
`@indi-nexus/react` and the `indi-nexus` Python package, so a given version number means
the same release across all three.

Version 0.1.0 is written up in the [repository changelog](../../../CHANGELOG.md), which
covered all three packages at the time. From 0.2.0, changes to this package are recorded
here.

<!-- --8<-- [start:releases] -->
