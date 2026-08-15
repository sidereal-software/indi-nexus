# Changelog

Releases of the `indi-nexus` Python package. The two npm packages ship at the same
version and keep their own changelogs, in
[web/packages/client](web/packages/client/CHANGELOG.md) and
[web/packages/react](web/packages/react/CHANGELOG.md). Version 0.1.0 below covers all
three, because it predates the split.

Written by [Release Please](https://github.com/googleapis/release-please) from the commit
messages on `main`. Do not edit it by hand.

<!-- --8<-- [start:releases] -->


## [0.2.0](https://github.com/sidereal-software/indi-nexus/compare/indi-nexus-v0.1.0...indi-nexus-v0.2.0) (2026-08-15)


### ⚠ BREAKING CHANGES

* **protocol:** timestamps on Vector, Message and DelProperty are timezone-aware UTC, so comparing one against a naive datetime.now() raises TypeError. A naive datetime passed to prop.set(timestamp=) or device.message(timestamp=) is read as UTC, not local. parse_indi() no longer raises on a malformed value; it returns fewer messages, and the count is on the parser. format_number changes at exact half ticks.

### Added

* **cli:** add Typer serve/run/monitor commands ([e583d5e](https://github.com/sidereal-software/indi-nexus/commit/e583d5eb80d9dc2824012bfd11053e5d1d2b21d1))
* **client:** add PropertyStore cache with subscriptions ([56e7950](https://github.com/sidereal-software/indi-nexus/commit/56e795026dbce8a3111d4f4bca9fc7d78b1143c8))
* **client:** add public send() for forwarding messages upstream ([9c573dd](https://github.com/sidereal-software/indi-nexus/commit/9c573dd4d6587611f956b02a532ccb13f260e985))
* **client:** add reconnecting IndiClient ([82a4cee](https://github.com/sidereal-software/indi-nexus/commit/82a4ceeaedbded855afd39a70c8e5730d429c597))
* **cli:** indi-nexus new scaffolds a runnable driver ([c53b24c](https://github.com/sidereal-software/indi-nexus/commit/c53b24c52d3b727b19bc791f3f84593a231738c3))
* **cli:** run drivers in-process with serve --device ([e19f168](https://github.com/sidereal-software/indi-nexus/commit/e19f168101713ab5f0971c4ecba66eb0b44df75a))
* **docs:** add a live weather demo running in the browser ([da64737](https://github.com/sidereal-software/indi-nexus/commit/da6473735649265121b2562f8ccb51a59254fb6f))
* **docs:** MkDocs Material site with live demo, both APIs, Pages deploy ([1da18e4](https://github.com/sidereal-software/indi-nexus/commit/1da18e4e87928f0156c6a701184a16ad70a74aef))
* **docs:** rebuild the weather demo around the real panel and a proper dashboard ([a6c8d2d](https://github.com/sidereal-software/indi-nexus/commit/a6c8d2daa34f3735fb628c004d9dd6138930542a))
* **docs:** redesign the custom UI as a dome wallboard ([cf67168](https://github.com/sidereal-software/indi-nexus/commit/cf671681cbd97e0ba82a2ed081c81dc81ca2c769))
* **driver:** add [@every](https://github.com/every) and [@on](https://github.com/on)_new decorators ([a9ee27e](https://github.com/sidereal-software/indi-nexus/commit/a9ee27ecee498cddfb82f5c0d28dde4b5f83076d))
* **driver:** add BoundProperty and Device base class ([4a9f7b3](https://github.com/sidereal-software/indi-nexus/commit/4a9f7b3501aafc7571ad5dda623a5a76a2379f0c))
* **driver:** add stdio runtime and package entrypoint ([7a841d8](https://github.com/sidereal-software/indi-nexus/commit/7a841d8f012483143c5eccf975dc67194874a0d1))
* **driver:** built-in CONNECTION lifecycle and connection-gated jobs ([1a32b14](https://github.com/sidereal-software/indi-nexus/commit/1a32b14be14e9f04c2d599e94edc6e7c234c919d))
* **driver:** serialize dispatch, type properties, and quiet the wire ([2824378](https://github.com/sidereal-software/indi-nexus/commit/2824378a9e68a2dd1d66f7bd3b21a053c81cf95e))
* **examples:** add a dome simulator driver ([aefacf1](https://github.com/sidereal-software/indi-nexus/commit/aefacf1b633e5739167f99c1d1b562efff34118f))
* **examples:** add a hardware-shaped weather station driver ([a7da59d](https://github.com/sidereal-software/indi-nexus/commit/a7da59d0b73306c4a2c4159b2b6abb4fa86e481d))
* **examples:** add a telescope simulator driver ([90ebb9e](https://github.com/sidereal-software/indi-nexus/commit/90ebb9e259496e93d2a79a6f91d988685295e56e))
* **examples:** add an Open-Meteo driver for real public data ([4a6def5](https://github.com/sidereal-software/indi-nexus/commit/4a6def52e38c93ac4b4e0a5f8b5f877821defbb1))
* **examples:** gate the dome behind CONNECTION; test both simulators ([3a9bc9a](https://github.com/sidereal-software/indi-nexus/commit/3a9bc9a0aca8d5efe43409e808ce80c523e5233f))
* **examples:** port libindi's CCD Simulator to the SDK ([2f0626a](https://github.com/sidereal-software/indi-nexus/commit/2f0626ab847697b18809d9928bf2b56d310b8ad4))
* **examples:** publish wind bearing and apparent temperature ([65d92bb](https://github.com/sidereal-software/indi-nexus/commit/65d92bbbb3c6eab4090e9adfbab48349ff4f2944))
* **examples:** serve any driver in the demo bridge via --device ([463826e](https://github.com/sidereal-software/indi-nexus/commit/463826e3db131df9383d3df2979caca89bd56fcc))
* **examples:** serve several drivers in one panel ([c3a325f](https://github.com/sidereal-software/indi-nexus/commit/c3a325fbfbfccc055a0e883ada07a5bdb6ee549f))
* **panel:** animate the messages rail and use a bottom drawer on mobile ([da4804d](https://github.com/sidereal-software/indi-nexus/commit/da4804d75779d44296a0f9fa2c5890cff11f6931))
* **panel:** backend-less demo build with an in-browser dome simulator ([460f072](https://github.com/sidereal-software/indi-nexus/commit/460f072594a08313128781dc179c34dabc055cb2))
* **panel:** disclose the messages panel from its own title bar ([705a33a](https://github.com/sidereal-software/indi-nexus/commit/705a33ad106830e42690fcd2a84031c5e65db0e3))
* **panel:** dock the message log as a right-hand sidebar ([c57e596](https://github.com/sidereal-software/indi-nexus/commit/c57e596b7a60840bf364fd68181b2aa292486d73))
* **panel:** dock the message log as a VS Code-style bottom panel ([69a87f4](https://github.com/sidereal-software/indi-nexus/commit/69a87f44d63e9945b57e51b81ab4532f1f5804e1))
* **panel:** dock the messages log as a collapsible side panel ([47ff543](https://github.com/sidereal-software/indi-nexus/commit/47ff5431ad8b2aa01800549a8790caa58779150a))
* **panel:** move the messages toggle into the sidebar menu ([d147f04](https://github.com/sidereal-software/indi-nexus/commit/d147f04fb0cf9d152e956ce8127c07931caeb0fc))
* **panel:** navbar-height messages bar, unread badge, and tooltips ([721e6c9](https://github.com/sidereal-software/indi-nexus/commit/721e6c96422388f41388752b10cd2536fb058b90))
* **panel:** toggle the messages sidebar from a header icon button ([007f781](https://github.com/sidereal-software/indi-nexus/commit/007f781a1de2a551588e424fb74fc653f1ed67dd))
* **protocol:** add enableBLOB message and BLOBPolicy ([60f3c08](https://github.com/sidereal-software/indi-nexus/commit/60f3c085410600c93b6f58ec52bbe7db1e60b420))
* **protocol:** add JSON codec and base64 BLOB serialization ([8195c92](https://github.com/sidereal-software/indi-nexus/commit/8195c9266e303708a52fda9219f3fbcf95cf08b3))
* **protocol:** add slugify and Element.from_labels ([97b067f](https://github.com/sidereal-software/indi-nexus/commit/97b067ffa693256adade71cc7b444fc6ff085290))
* **protocol:** add typed INDI protocol core with XML codec ([c39975a](https://github.com/sidereal-software/indi-nexus/commit/c39975ab101a8447242e540c1346e84a6e381c77))
* **protocol:** pure vector accessors for handler ergonomics ([fe5af28](https://github.com/sidereal-software/indi-nexus/commit/fe5af288e194840b08b49761080e1b94fcfcd1e5))
* **react:** add per-kind value hooks ([28f27a2](https://github.com/sidereal-software/indi-nexus/commit/28f27a20e6fb3075b55c219be65a91ea8eebd79d))
* **react:** add the shadcn accordion primitive ([5341f4f](https://github.com/sidereal-software/indi-nexus/commit/5341f4f13e405b5a4a18821c178c2e9e3ce32d5b))
* **react:** add the shadcn drawer primitive ([9180b8f](https://github.com/sidereal-software/indi-nexus/commit/9180b8f16b5ce728b21789105612315632e6c853))
* **react:** export the test harness as @indi-nexus/react/testing ([8440709](https://github.com/sidereal-software/indi-nexus/commit/8440709cf6978b8e8d34d9b6d244b7c28e34ae9c))
* **testing:** add DeviceHarness ([a737146](https://github.com/sidereal-software/indi-nexus/commit/a737146755651b88049c1a6d8fdcd63a71628e5f))
* **web:** add @indi-nexus/client transport and property store ([6c77924](https://github.com/sidereal-software/indi-nexus/commit/6c779246a67615d3edd2bc5b5f57e11dcd3f0c0b))
* **web:** add @indi-nexus/react hooks and shadcn/ui components ([c46ab2d](https://github.com/sidereal-software/indi-nexus/commit/c46ab2d9474b084f77630e5a18d2f9aba374a189))
* **web:** add Bridge and FastAPI app (WebSocket + REST snapshot) ([5048e91](https://github.com/sidereal-software/indi-nexus/commit/5048e9177aa44e44a7debb006928e57435fdadb1))
* **web:** add self-contained debug inspector page ([f6441b9](https://github.com/sidereal-software/indi-nexus/commit/f6441b9ffb1db6d743d761dc8ee745f00eaf8c5b))
* **web:** add the reference panel app ([2d7e9c2](https://github.com/sidereal-software/indi-nexus/commit/2d7e9c2edafcb1b8ab63802b07ba30d4be6bde2a))
* **web:** debug-info display setting for technical INDI detail ([f38af6f](https://github.com/sidereal-software/indi-nexus/commit/f38af6f4297cdc72b747aaca8165f88a38bae971))
* **web:** live current-value readouts on writable elements ([c631c1e](https://github.com/sidereal-software/indi-nexus/commit/c631c1e0468239fed416255fb586fcc2efd0f8c3))
* **web:** mark the selected switch in the action colour and pulse Busy ([cf55441](https://github.com/sidereal-software/indi-nexus/commit/cf554417fc66c103499a85e057de38cf9d800226))
* **web:** serve the built panel from FastAPI; add demo bridge harness ([eff8e1a](https://github.com/sidereal-software/indi-nexus/commit/eff8e1a588d4d318c98453c9dea12eafc5a634e6))
* **web:** stack message-log entries and follow the newest ([cd91cdf](https://github.com/sidereal-software/indi-nexus/commit/cd91cdfd05a42dd9449e320aaca28fab4ba396b2))
* **web:** useElement hook for single-value reads ([b1623cf](https://github.com/sidereal-software/indi-nexus/commit/b1623cf3436bf857965ab3ae76259d4b395f7755))


### Fixed

* **build:** keep node_modules out of the sdist and the package sources in ([718abd2](https://github.com/sidereal-software/indi-nexus/commit/718abd24febf31c62526e7e9646698edb45bc1c0))
* **ci:** build workspace packages before typecheck and test ([072e32f](https://github.com/sidereal-software/indi-nexus/commit/072e32f3e33ad08b8b706d150e85d2a73e697571))
* **ci:** give Mermaid a browser to render diagrams with ([aa92a79](https://github.com/sidereal-software/indi-nexus/commit/aa92a790e656f7c4d4362baf81b4b600a47a881a))
* **ci:** pin pnpm version for pnpm/action-setup ([e977c47](https://github.com/sidereal-software/indi-nexus/commit/e977c473f34311f2150479df6d62b5e4e034a815))
* **ci:** pin setup-uv to a tag that exists ([965440c](https://github.com/sidereal-software/indi-nexus/commit/965440ccb04785d2b4993eb8928cef6f1b887834))
* **client:** ignore a socket that has already been superseded ([7b4d0e2](https://github.com/sidereal-software/indi-nexus/commit/7b4d0e283f134032c7500a1eb10cde5640b64b2a))
* **client:** keep a property's state when a set does not carry one ([dfa9a46](https://github.com/sidereal-software/indi-nexus/commit/dfa9a4652099f0863642966a1c4f13b3bb12357d))
* **client:** key BLOB policies on a pair, and drop non-object frames ([ff2d87e](https://github.com/sidereal-software/indi-nexus/commit/ff2d87e5ec91bfe3ad5f7957f76723407f6a80b7))
* **client:** render numbers the way the wire renders them ([9903f21](https://github.com/sidereal-software/indi-nexus/commit/9903f216257752a333f67bdf89d9d3c13d5c6237))
* **demo:** put the simulators back in step with their drivers ([0c475d8](https://github.com/sidereal-software/indi-nexus/commit/0c475d83568a72256999783f168d6fa41407126a))
* **driver:** gate [@every](https://github.com/every) jobs on setup() completion ([7ceeabd](https://github.com/sidereal-software/indi-nexus/commit/7ceeabdb11ba3949d46657084f90ca411f4dd61d))
* **driver:** honor the getProperties device filter ([856768b](https://github.com/sidereal-software/indi-nexus/commit/856768b5eeb90af1862b32fbc9964ba3fc5daacd))
* **driver:** ignore client writes addressed to other devices ([31ad723](https://github.com/sidereal-software/indi-nexus/commit/31ad723fb2eb749c61ca2838add941cb2055c608))
* **driver:** survive exceptions from [@on](https://github.com/on)_new handlers and setup() ([cce961f](https://github.com/sidereal-software/indi-nexus/commit/cce961fc276c89939f89de237c59625f062825a4))
* **examples:** power-gate the demo animation and accept partial switch writes ([95d1c99](https://github.com/sidereal-software/indi-nexus/commit/95d1c999a2714713b62be6db178697864eb05acb))
* **protocol:** make `name in vector` tell the truth ([30275d6](https://github.com/sidereal-software/indi-nexus/commit/30275d63316fb0e9ab932e8d00b913638cf7aebd))
* **protocol:** survive a hostile peer and stamp timestamps in UTC ([bfe2ddf](https://github.com/sidereal-software/indi-nexus/commit/bfe2ddfbc875320b8740f3b4aeba076d8b574f9c))
* **react:** restore pointer cursor on enabled buttons under Tailwind v4 ([42bb085](https://github.com/sidereal-software/indi-nexus/commit/42bb0852b741ae2942d506ef369d5af92bb158a7))
* **transport:** add close to the transport contract and release sockets ([0fdc210](https://github.com/sidereal-software/indi-nexus/commit/0fdc210debbbc6f75705d6b043ca441b81355b4c))
* **typing:** ship a py.typed marker ([4664027](https://github.com/sidereal-software/indi-nexus/commit/46640271c20b9c77bdcf71f453a6b057bed26a19))
* **web:** buffer INDI messages and replay them to late-joining viewers ([93c258e](https://github.com/sidereal-software/indi-nexus/commit/93c258e1550567401dd1ec4b56f652635b05661a))
* **web:** drop the tick and stop a switch deselecting itself ([2fc020d](https://github.com/sidereal-software/indi-nexus/commit/2fc020de622505fdcea94709a6bb272097b93fb9))
* **web:** make the active member of a switch vector legible ([fdfd135](https://github.com/sidereal-software/indi-nexus/commit/fdfd135876964c06ec0791465ac1febe0e9e6835))
* **web:** make the panel and the wallboard work on a phone ([ffc1d7e](https://github.com/sidereal-software/indi-nexus/commit/ffc1d7ecd43d74a56d9a90db4535934b9ab3ac0d))
* **web:** stack writable-element rows so labels and readouts always fit ([aec4436](https://github.com/sidereal-software/indi-nexus/commit/aec443602babc882572018cc4fcf4d031c0a8f11))
* **web:** start the bridge without waiting for indiserver ([e0274f3](https://github.com/sidereal-software/indi-nexus/commit/e0274f345c1e70db7b9d22ed0475e0c73806f450))
* **web:** track src/lib/utils.ts (gitignored by the Python lib/ rule) ([b777e09](https://github.com/sidereal-software/indi-nexus/commit/b777e0924614c7e4c327c38eb2dd6036a81e0650))
* **web:** use relative imports in @indi-nexus/react instead of the @/ alias ([8d1bd3a](https://github.com/sidereal-software/indi-nexus/commit/8d1bd3aa2d72b4a63060529182ed6822863d6e46))


### Packaging

* add httpx dev dependency and filter starlette test warning ([c2ed83c](https://github.com/sidereal-software/indi-nexus/commit/c2ed83c6500237e5fc178c96437d3d5475ce18bc))
* automate PyPI and npm releases ([097a3b9](https://github.com/sidereal-software/indi-nexus/commit/097a3b9dfdea435e1063f845baac5e3eecf303f1))
* bundle the reference panel into the wheel ([e7dd273](https://github.com/sidereal-software/indi-nexus/commit/e7dd2733eb646a7325f3bf0c40ee1da34a7b9ccf))
* **ci:** move every action off the deprecated Node 20 runtime ([bacd233](https://github.com/sidereal-software/indi-nexus/commit/bacd23390b4324c87e1db28892272f36a72ccffd))
* keep breaking changes on the minor while below 1.0 ([1a9d647](https://github.com/sidereal-software/indi-nexus/commit/1a9d6475acc8b39ccccadd160262f103ea7311b3))
* let Release Please own the changelog and drop towncrier ([8a37c37](https://github.com/sidereal-software/indi-nexus/commit/8a37c37ffef52b614301593c51575ebe2693c2ff))
* manage the changelog with towncrier ([990b29b](https://github.com/sidereal-software/indi-nexus/commit/990b29bf70cd8bd8178d3b424f9c4fe25f04ab7e))
* require Python 3.12 and drop the anyio dependency ([128d042](https://github.com/sidereal-software/indi-nexus/commit/128d0427d1515e24f40bdef1486064702a3405db))
* set up Python packaging, dependencies, and dev tooling ([7ff13cd](https://github.com/sidereal-software/indi-nexus/commit/7ff13cd24a74b8db20350a4eea8d9d15828140f1))
* test and declare Python 3.13 and 3.14 ([f962290](https://github.com/sidereal-software/indi-nexus/commit/f962290dba22982f59f281564a383191327348e0))


### Documentation

* add DEVELOPMENT.md with the full command reference ([40a8192](https://github.com/sidereal-software/indi-nexus/commit/40a8192ba64346c0360e05aa408d02db723e9acb))
* add quickstart and command reference to README ([9df062f](https://github.com/sidereal-software/indi-nexus/commit/9df062fbbb92fb902975f972e7463aee38be5ab5))
* add the real-data tutorial and its custom UI ([47980b1](https://github.com/sidereal-software/indi-nexus/commit/47980b1be722591190f17e493fe22c166e50b749))
* adopt Python 3.12, asyncio, and NumPy-docstring conventions ([802a16a](https://github.com/sidereal-software/indi-nexus/commit/802a16abaf0d3a09184d1f71eeb8d0d65ce1b82d))
* **claude:** split the guidance by area and add the global working rules ([da96e31](https://github.com/sidereal-software/indi-nexus/commit/da96e31e0a60bdd82884344a89748065683684a8))
* correct the macOS install claim and cut repetition ([a9e8027](https://github.com/sidereal-software/indi-nexus/commit/a9e8027d2198c9b211da33a9a069001b83484127))
* cover the new SDK surface, port guide, and mermaid diagrams ([f94fd80](https://github.com/sidereal-software/indi-nexus/commit/f94fd8084c333b9bb9ef82d05340af7c11e46602))
* cut duplication and fix broken cross-references ([44781e8](https://github.com/sidereal-software/indi-nexus/commit/44781e8c157e494d056881cc6eaae9417e17bdac))
* cut the 0.1.0 changelog for today, and write up releasing ([93c1a26](https://github.com/sidereal-software/indi-nexus/commit/93c1a2639d8c1ba618a83aa9da8639ad4de99671))
* describe INDINexus, stack, and workflows in README and CLAUDE.md ([e69104d](https://github.com/sidereal-software/indi-nexus/commit/e69104df8396a4ffaab0e2d4b70073243aaf649e))
* docstring type fields are plain text, not backticked ([300b85a](https://github.com/sidereal-software/indi-nexus/commit/300b85ae46cdb3f7e1a02f058a2f48f512592845))
* document the examples and the three ways to run a driver ([1fc9f03](https://github.com/sidereal-software/indi-nexus/commit/1fc9f03b65af038fa4de9b2c7b70b24e8bfbbee3))
* **driver:** add Numpydoc parameter types to docstrings ([429d920](https://github.com/sidereal-software/indi-nexus/commit/429d920488e147a91bb61561bdc83ae4b9653fca))
* **driver:** document the driver SDK and add demo device ([f9d8dae](https://github.com/sidereal-software/indi-nexus/commit/f9d8dae8eacbae9e0f025a66abeadf3b475bb19f))
* **driver:** NumPy-style docstrings across the driver SDK ([7ed606a](https://github.com/sidereal-software/indi-nexus/commit/7ed606a8fa73517a2a242fbc7a4896057a45c65b))
* drop backticks from docstring type fields ([5c733ee](https://github.com/sidereal-software/indi-nexus/commit/5c733ee830b862f673d9f53fa07fc7f5e5b27c5d))
* **examples:** add monitor_client example with tests ([3d1f137](https://github.com/sidereal-software/indi-nexus/commit/3d1f137df55e21dac76a9cec52e51b6100654ddc))
* **examples:** docstring the demo device methods ([f12b7f5](https://github.com/sidereal-software/indi-nexus/commit/f12b7f5a8712d3272a8db325c8cb5fa05ee3f940))
* feature all three simulators in the demo ([6638357](https://github.com/sidereal-software/indi-nexus/commit/66383570d48f5ba4c24a4c25ace11cd920f0ea76))
* fix the claims an audit found were no longer true ([65c8cc9](https://github.com/sidereal-software/indi-nexus/commit/65c8cc9ec053a5a61a780456f05af1013a7fd0f4))
* focus the README on quickstart and link the development guide ([82a9fdc](https://github.com/sidereal-software/indi-nexus/commit/82a9fdce9341e4023d4c4b787cf9f4ddf332cb38))
* general refactor - tighten prose and update project URLs ([7b3b76e](https://github.com/sidereal-software/indi-nexus/commit/7b3b76ea475482f303db84760dcfc11600678150))
* improve mermaid diagram contrast on light backgrounds ([ff1c796](https://github.com/sidereal-software/indi-nexus/commit/ff1c796f8325a3ce5a6ca5581a3d5cff77d5c7e1))
* install from PyPI, and be clear indiserver is the hub ([25bba24](https://github.com/sidereal-software/indi-nexus/commit/25bba241c200b5f922b38c83ac6ec56df2c578d4))
* let the diagrams follow the theme, and validate them in CI ([40152d7](https://github.com/sidereal-software/indi-nexus/commit/40152d75be5b5403159f19a43445c879a76f01b4))
* link the weather demo and give it a nav tab ([893a139](https://github.com/sidereal-software/indi-nexus/commit/893a139b62939fde4484cd2f7827f3ee8f59ae29))
* make the flat-field lamp a real example and run it in the browser ([21ddd52](https://github.com/sidereal-software/indi-nexus/commit/21ddd525c830f7b92c0cd8202c8e2bc0a84f535c))
* mark client layer done; refresh README ([8f0d5da](https://github.com/sidereal-software/indi-nexus/commit/8f0d5da3f513c5334494488fe3f7cd14f7b0df50))
* mark M5 done and document the frontend ([e902251](https://github.com/sidereal-software/indi-nexus/commit/e902251b31dba8e8737d61be4031e761a8238f86))
* mark web bridge and CLI done; add bridge E2E and docs ([992d401](https://github.com/sidereal-software/indi-nexus/commit/992d401f186a601b436418740d050c0032e9e275))
* **protocol:** add Numpydoc parameter types to docstrings ([d95cb56](https://github.com/sidereal-software/indi-nexus/commit/d95cb5673d56a2fa2bed26a82d319ed647c366ad))
* **protocol:** NumPy-style docstrings across the protocol layer ([12ae2d9](https://github.com/sidereal-software/indi-nexus/commit/12ae2d922bc0b7ef19bdfda38af87d2bdbf1c2c9))
* rewrite the public docs for a first-time reader ([02abc5c](https://github.com/sidereal-software/indi-nexus/commit/02abc5cbef6542154cc72a50e36bce3c214c63bd))
* serve the live demo as its own page and move the site to a subdomain ([f7fd934](https://github.com/sidereal-software/indi-nexus/commit/f7fd93494bf72291e8833d86e5c1da53ed39e241))
* specify Numpydoc parameter formatting rules ([79c7554](https://github.com/sidereal-software/indi-nexus/commit/79c7554d9895096d0a6c0b6869aab79a05763772))
* split the changelog into sections and publish it on the docs site ([e91502e](https://github.com/sidereal-software/indi-nexus/commit/e91502e254a0f5558952d8ddde3455e4528d33be))
* **tests:** add NumPy-style docstrings to the test suite ([0bcb910](https://github.com/sidereal-software/indi-nexus/commit/0bcb91042ed9d05ad8e3cd0da6a3aaf5f302ffc8))
* **tests:** type the docstring parameter entries in the suite ([7b2c470](https://github.com/sidereal-software/indi-nexus/commit/7b2c470ed7598cc26a4483c03c5778f9615589da))
* tighten CLAUDE.md and point it at DEVELOPMENT.md ([73509ad](https://github.com/sidereal-software/indi-nexus/commit/73509ad496d60b8d2d20ea3d4b0ec8ac817fc1a6))
* update CLAUDE.md for the transport, runtime, and bridge changes ([79b9b93](https://github.com/sidereal-software/indi-nexus/commit/79b9b9368d299af72fe7b646dfd6ef18fab645a5))
* **web:** add readmes and licences to the published npm packages ([169e304](https://github.com/sidereal-software/indi-nexus/commit/169e304853614769b349644bc7e4a065a5e460ac))


### Changed

* **driver:** extract shared transport contract ([bbfb996](https://github.com/sidereal-software/indi-nexus/commit/bbfb9967a1a0630597dd9eb5dac86bf8d4119cbc))
* **driver:** replace anyio with asyncio in the runtime ([7f65305](https://github.com/sidereal-software/indi-nexus/commit/7f65305b6439eec32b34dafeccd7886d8a4bed81))
* **examples:** adopt the SDK connection surface and accessors ([00cb80d](https://github.com/sidereal-software/indi-nexus/commit/00cb80d65f7b73220febd253677a955b2b5d75f2))
* **protocol:** use stdlib StrEnum for the wire enums ([e4ff825](https://github.com/sidereal-software/indi-nexus/commit/e4ff82537023d5bb4cae3cb92463339b2eab85ab))
* **web:** map an INDI state to its colour in one place ([2084e66](https://github.com/sidereal-software/indi-nexus/commit/2084e669ebc94622dadc7b938bfa206273da3df5))

## 0.1.0 - 2026-08-11


### Python package (indi-nexus)

#### Added

- A nightly interop suite that runs against a real `indiserver` and real libindi drivers.
  Every other test here reads our own XML with our own parser, which is self-consistent by
  construction and so cannot catch a deviation from the spec; these put libindi on the other
  side of the wire. It covers libindi's own clients driving our drivers, our client against
  all twelve simulators libindi ships, a differential comparison against `indi_getprop`, BLOB
  delivery, reconnecting to a real socket, and a browser driving a C++ driver through the
  whole stack. Real traffic captured from those drivers is committed as a fixture and replayed
  by the fast suite, so a pull request gets the benefit without libindi installed.
- `examples/flat_panel.py`: the flat-field lamp driver the "Writing a driver" guide builds
  line by line. It was previously only a listing in the guide, so nothing checked it still
  ran; it is now a real example covered by the test suite, and the guide points at it.
- `indi-nexus serve --device module:Class` runs drivers inside the web process, so a driver
  can be tried on screen with only `pip install indi-nexus` and no `indiserver` to install
  first. Repeat the flag for several devices. It is a development convenience, not a hub: it
  serves one client and stops with the command. `indiserver` remains what anything real runs
  under, and `serve` without `--device` connects to it exactly as before. This replaces
  `examples/demo_bridge.py`, whose hub now lives in the package as
  `indi_nexus.web.InProcessHub`.

#### Fixed

- `"RA" in vector` now answers truthfully. `Vector` defined `__getitem__` without
  `__contains__`, so Python fell back to indexing 0, 1, 2 against a name lookup and returned
  `False` for an element that was present, without raising. The interop suite found it by
  writing the obvious thing.
- `indi-nexus serve` now starts even when `indiserver` is unreachable, instead of hanging in
  startup with no output. The panel loads and reports a disconnected state, and the bridge
  connects on its own once `indiserver` appears. `IndiClient.start()` gained a `wait` keyword
  for this; its default is unchanged, so scripts and monitors still block until the first
  connection.

#### Packaging

- Published to PyPI as `indi-nexus`, so `pip install indi-nexus` gets the driver SDK, the
  async client, the web bridge and the bundled reference panel. Releases are cut from `main`
  by release-please and uploaded with trusted publishing, so no registry credentials are
  stored in the repository.
- The source distribution no longer bundles `web/node_modules` (about 8 MB of build
  dependencies), and it now contains the TypeScript sources of `@indi-nexus/client` and
  `@indi-nexus/react`, which were being dropped from it.

#### Documentation

- Getting started now installs from PyPI instead of cloning the repository and building the
  frontend. The panel is compiled into the wheel, so `pip install indi-nexus` is the whole
  setup, and the first driver you see running is one you scaffolded rather than an example
  that only exists in a checkout.
- The architecture diagrams now follow whichever theme they are rendered in. They carried a
  hardcoded light palette, so on a dark page the boxes became a bright island and the labels
  went unreadable; ownership is shown with the border instead of colour. CI validates every
  diagram with Mermaid's own CLI, so a broken one fails the build rather than rendering as an
  empty box.


### Frontend (@indi-nexus/client, @indi-nexus/react)

#### Changed

- Busy now pulses, on both the state badge and the status-light dots. It is the one state that
  means "still happening", and a still badge cannot tell an instrument mid-move from one that
  stopped there. The pulse holds still for anyone whose system asks for reduced motion.
- Every indicator that shows an INDI state now reads its colour from one place. A component
  cannot build a Tailwind class name at runtime, so each of the five places that showed a
  state carried its own copy of the four-way mapping, and they drifted. Elements now declare
  `data-indi-state` and the theme sets `--indi-state` from it, so a badge, a dot, a bar and an
  SVG fill can each use whichever CSS property they need. `StateDot` is exported for frontends
  built on the hooks.

#### Fixed

- The selected member of a switch vector is now unmistakable, and safer to click. It was drawn
  with the same `accent` token the toggles hover to, so a hovered unselected member looked
  identical to the selected one, and the fill itself was nearly invisible against the card; it
  now wears the same teal as the Set button, a colour hovering never reaches. Clicking the
  member that is already on no longer turns it off. Under `OneOfMany` exactly one member is on
  by definition, so there was no such state to reach - a stray click on a lit "On" would have
  switched the instrument off. Selecting the member you want is now the only way to change it.
  `AtMostOne`, which genuinely permits none, still clears that way.

#### Packaging

- Published to npm as `@indi-nexus/client` and `@indi-nexus/react`, released in lockstep with
  the Python package and uploaded with trusted publishing.

#### Documentation

- A flat-panel demo on the documentation site, running the guide's driver as an in-browser
  simulator behind the panel that ships in the wheel, so the driver a reader has just been
  taught can be operated with nothing installed.
- `@indi-nexus/client` and `@indi-nexus/react` now ship a README and a copy of the licence, so
  both have documentation on their npm pages.
