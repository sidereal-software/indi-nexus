# Changelog

## [0.3.0](https://github.com/sidereal-software/indikit/compare/react-v0.2.0...react-v0.3.0) (2026-08-20)


### ⚠ BREAKING CHANGES

* **theme:** `--primary` is a blue rather than a neutral in the light and dark schemes, and every chrome token in `.night` is now red. A consumer who matched the previous neutral primary, or who relied on `.night` being a grey scheme, has to move.
* **theme:** every colour token in `@indikit/react`'s theme changes value, including all four `--state-*` fills and their foregrounds, and a third scheme (`.night`) joins light and dark. A consumer who hardcoded any token's hex, or who toggles themes by writing the `dark` class directly, has to move: `night` is expressed as `dark night` together. `useTheme` now returns `cycle` rather than `toggle` and reports three schemes.
* the distribution, the import package and the CLI are all `indikit`; the environment prefix is `INDIKIT_`; the npm packages are `@indikit/client` and `@indikit/react`; and the driver property `NEXUS_CONFIG_PERSISTED` is now `INDIKIT_CONFIG_PERSISTED`. Nothing was ever published under the old names, so no upgrade path is provided.
* **a11y:** `AlertAnnouncer` is renamed to `StatusAnnouncer`. It now announces three things and only one of them is an alert: a vector entering Alert, an operator-initiated write reaching a settled state, and connection loss or recovery. The new name matches the `role="status"` it renders.
* **react:** DeviceConfigCard and DeviceConfigCardProps are removed from @indi-nexus/react and replaced by DeviceConfigDialog and DeviceConfigDialogProps. The card was deleted rather than kept alongside the dialog: nothing used it once the panel stopped pinning it, and two components rendering identical copy is the pair that drifts.

### Added

* **docs:** repaint the site in an astronomy palette that passes AA ([5b916bb](https://github.com/sidereal-software/indikit/commit/5b916bb22d68ac6ff6194463deb793677f111de8))
* **driver:** publish which properties Save will write ([e1b2cc1](https://github.com/sidereal-software/indikit/commit/e1b2cc15e9b5cf3e3dc38c13aa76a655b65eee58))
* **react:** give CONFIG_PROCESS a card that tells the truth ([e526d11](https://github.com/sidereal-software/indikit/commit/e526d11d43c8065963088b361802b61a03993f51))
* **react:** move configuration to a sidebar entry and a modal ([d3506f1](https://github.com/sidereal-software/indikit/commit/d3506f1c25874b360349c66a64e942f8751fedeb))
* **theme:** a blue action, and a red safelight for night ([0bb3dcc](https://github.com/sidereal-software/indikit/commit/0bb3dcce4e2157301e6df3ead5e521db0f0f132f))
* **theme:** commit the Emission Spectrum identity across three schemes ([e2d9092](https://github.com/sidereal-software/indikit/commit/e2d909248661c4ab0d1c434c844299691d5ba54c))
* **theme:** self-host the faces, and let value carry the write action ([58e427f](https://github.com/sidereal-software/indikit/commit/58e427f292a7e30149c52e349eb0fa2f97abb0f8))
* **theme:** the selected switch member wears the action colour ([1875524](https://github.com/sidereal-software/indikit/commit/1875524b78fcbb1316abdf748187ae51ab0a1c38))
* **web:** version the browser JSON contract with a hello frame ([6a4333a](https://github.com/sidereal-software/indikit/commit/6a4333ac00400652ca3f65649d35909a46802548))


### Fixed

* **a11y:** correct contrast, targets and motion from theme.css ([d37ca55](https://github.com/sidereal-software/indikit/commit/d37ca558033ede615659a7d7db482d1ca48451df))
* **client:** fall back to the element name when a label is blank ([a887fbf](https://github.com/sidereal-software/indikit/commit/a887fbfdcd29bdd94c9e0e283d940792f199193d))
* **panel:** give a stop command the one action colour, not its own red ([83e3e71](https://github.com/sidereal-software/indikit/commit/83e3e716ca57099bdba8f5cd442c646cfac1e12b))
* **panel:** nest configuration under its device, and draw a command as a button ([ba7c8ea](https://github.com/sidereal-software/indikit/commit/ba7c8eac5a3f90e29dd9ea77dab139b61a265203))
* **protocol:** emit standard base64 for a BLOB, not the URL-safe alphabet ([064d1c7](https://github.com/sidereal-software/indikit/commit/064d1c72cd342d7adacb246099c44eaa789c2054))
* **react:** give dark mode a destructive colour and a visible action colour ([ad9bea8](https://github.com/sidereal-software/indikit/commit/ad9bea8425f7fa6bbb88357322bd1ab3c7d52912))
* **react:** make the panel usable without sight or a mouse ([6d39585](https://github.com/sidereal-software/indikit/commit/6d395859eaa9f10d938ede0f86f958c3b45800e7))
* **react:** read an offsetless INDI timestamp as UTC ([3634466](https://github.com/sidereal-software/indikit/commit/3634466547767f42e32007e1dca5d5c13bd55c86))
* **theme:** let a card be a surface, not a drawn box ([e1cd3d1](https://github.com/sidereal-software/indikit/commit/e1cd3d1c61e5543a93d82bbb26c2c4054732bb2a))
* **web:** a device with no properties is not a missing device ([a74467b](https://github.com/sidereal-software/indikit/commit/a74467b14e01ca2a6643b8770d02edf65ee1d5a9))


### Performance

* **react:** memoise the property grid ([0c99a33](https://github.com/sidereal-software/indikit/commit/0c99a337820658a39296cab1f70101b8e1129aca))


### Documentation

* give the React layer equal billing and teach with a focuser ([1a6d861](https://github.com/sidereal-software/indikit/commit/1a6d8611b16ca419c94322411208e24438ad7d0a))
* reconcile every document with the three new surfaces ([9c5c13c](https://github.com/sidereal-software/indikit/commit/9c5c13c050c4d5b0270acf4ae37774d58fb3a690))
* reconcile the guides with a milestone they missed ([d7be286](https://github.com/sidereal-software/indikit/commit/d7be2863722d5cc93413499bcdd409408d9faad1))
* reconcile the guides, the register and the conventions ([bdb2571](https://github.com/sidereal-software/indikit/commit/bdb2571bec68919c8b58f40096b4e7b7a41bb928))
* rewrite the guides and READMEs in a plainer tone ([d6ad6cd](https://github.com/sidereal-software/indikit/commit/d6ad6cdd7e3fad2146ae609a31c36d7c9caee04e))


### Changed

* rename the project to INDIkit ([1b5cfd6](https://github.com/sidereal-software/indikit/commit/1b5cfd629a17ffd08c92866df6604ddf79b95c73))

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
