# Changelog

## [0.2.0](https://github.com/sidereal-software/indi-nexus/compare/react-v0.1.0...react-v0.2.0) (2026-08-15)


### Added

* **docs:** add a live weather demo running in the browser ([da64737](https://github.com/sidereal-software/indi-nexus/commit/da6473735649265121b2562f8ccb51a59254fb6f))
* **panel:** dock the messages log as a collapsible side panel ([47ff543](https://github.com/sidereal-software/indi-nexus/commit/47ff5431ad8b2aa01800549a8790caa58779150a))
* **react:** add per-kind value hooks ([28f27a2](https://github.com/sidereal-software/indi-nexus/commit/28f27a20e6fb3075b55c219be65a91ea8eebd79d))
* **react:** add the shadcn accordion primitive ([5341f4f](https://github.com/sidereal-software/indi-nexus/commit/5341f4f13e405b5a4a18821c178c2e9e3ce32d5b))
* **react:** add the shadcn drawer primitive ([9180b8f](https://github.com/sidereal-software/indi-nexus/commit/9180b8f16b5ce728b21789105612315632e6c853))
* **react:** export the test harness as @indi-nexus/react/testing ([8440709](https://github.com/sidereal-software/indi-nexus/commit/8440709cf6978b8e8d34d9b6d244b7c28e34ae9c))
* **web:** add @indi-nexus/react hooks and shadcn/ui components ([c46ab2d](https://github.com/sidereal-software/indi-nexus/commit/c46ab2d9474b084f77630e5a18d2f9aba374a189))
* **web:** debug-info display setting for technical INDI detail ([f38af6f](https://github.com/sidereal-software/indi-nexus/commit/f38af6f4297cdc72b747aaca8165f88a38bae971))
* **web:** live current-value readouts on writable elements ([c631c1e](https://github.com/sidereal-software/indi-nexus/commit/c631c1e0468239fed416255fb586fcc2efd0f8c3))
* **web:** mark the selected switch in the action colour and pulse Busy ([cf55441](https://github.com/sidereal-software/indi-nexus/commit/cf554417fc66c103499a85e057de38cf9d800226))
* **web:** stack message-log entries and follow the newest ([cd91cdf](https://github.com/sidereal-software/indi-nexus/commit/cd91cdfd05a42dd9449e320aaca28fab4ba396b2))
* **web:** useElement hook for single-value reads ([b1623cf](https://github.com/sidereal-software/indi-nexus/commit/b1623cf3436bf857965ab3ae76259d4b395f7755))


### Fixed

* **react:** restore pointer cursor on enabled buttons under Tailwind v4 ([42bb085](https://github.com/sidereal-software/indi-nexus/commit/42bb0852b741ae2942d506ef369d5af92bb158a7))
* **web:** buffer INDI messages and replay them to late-joining viewers ([93c258e](https://github.com/sidereal-software/indi-nexus/commit/93c258e1550567401dd1ec4b56f652635b05661a))
* **web:** drop the tick and stop a switch deselecting itself ([2fc020d](https://github.com/sidereal-software/indi-nexus/commit/2fc020de622505fdcea94709a6bb272097b93fb9))
* **web:** make the active member of a switch vector legible ([fdfd135](https://github.com/sidereal-software/indi-nexus/commit/fdfd135876964c06ec0791465ac1febe0e9e6835))
* **web:** stack writable-element rows so labels and readouts always fit ([aec4436](https://github.com/sidereal-software/indi-nexus/commit/aec443602babc882572018cc4fcf4d031c0a8f11))
* **web:** track src/lib/utils.ts (gitignored by the Python lib/ rule) ([b777e09](https://github.com/sidereal-software/indi-nexus/commit/b777e0924614c7e4c327c38eb2dd6036a81e0650))
* **web:** use relative imports in @indi-nexus/react instead of the @/ alias ([8d1bd3a](https://github.com/sidereal-software/indi-nexus/commit/8d1bd3aa2d72b4a63060529182ed6822863d6e46))


### Packaging

* automate PyPI and npm releases ([097a3b9](https://github.com/sidereal-software/indi-nexus/commit/097a3b9dfdea435e1063f845baac5e3eecf303f1))
* let Release Please own the changelog and drop towncrier ([8a37c37](https://github.com/sidereal-software/indi-nexus/commit/8a37c37ffef52b614301593c51575ebe2693c2ff))


### Documentation

* add the real-data tutorial and its custom UI ([47980b1](https://github.com/sidereal-software/indi-nexus/commit/47980b1be722591190f17e493fe22c166e50b749))
* cut duplication and fix broken cross-references ([44781e8](https://github.com/sidereal-software/indi-nexus/commit/44781e8c157e494d056881cc6eaae9417e17bdac))
* fix the claims an audit found were no longer true ([65c8cc9](https://github.com/sidereal-software/indi-nexus/commit/65c8cc9ec053a5a61a780456f05af1013a7fd0f4))
* rewrite the public docs for a first-time reader ([02abc5c](https://github.com/sidereal-software/indi-nexus/commit/02abc5cbef6542154cc72a50e36bce3c214c63bd))
* **web:** add readmes and licences to the published npm packages ([169e304](https://github.com/sidereal-software/indi-nexus/commit/169e304853614769b349644bc7e4a065a5e460ac))


### Changed

* **web:** map an INDI state to its colour in one place ([2084e66](https://github.com/sidereal-software/indi-nexus/commit/2084e669ebc94622dadc7b938bfa206273da3df5))

## @indi-nexus/react changelog

Releases of the React hooks and components. They ship at the same version as
`@indi-nexus/client` and the `indi-nexus` Python package, so a given version number means
the same release across all three.

Version 0.1.0 is written up in the [repository changelog](../../../CHANGELOG.md), which
covered all three packages at the time. From 0.2.0, changes to this package are recorded
here.

<!-- --8<-- [start:releases] -->
