# Changelog

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
