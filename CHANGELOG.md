# Changelog

Releases of the `indi-nexus` Python package. The two npm packages ship at the same
version and keep their own changelogs, in
[web/packages/client](web/packages/client/CHANGELOG.md) and
[web/packages/react](web/packages/react/CHANGELOG.md). Version 0.1.0 below covers all
three, because it predates the split.

Written by [Release Please](https://github.com/googleapis/release-please) from the commit
messages on `main`. Do not edit it by hand.

<!-- --8<-- [start:releases] -->


## [0.3.0](https://github.com/sidereal-software/indikit/compare/indikit-v0.2.0...indikit-v0.3.0) (2026-08-20)


### ⚠ BREAKING CHANGES

* **theme:** `--primary` is a blue rather than a neutral in the light and dark schemes, and every chrome token in `.night` is now red. A consumer who matched the previous neutral primary, or who relied on `.night` being a grey scheme, has to move.
* **theme:** every colour token in `@indikit/react`'s theme changes value, including all four `--state-*` fills and their foregrounds, and a third scheme (`.night`) joins light and dark. A consumer who hardcoded any token's hex, or who toggles themes by writing the `dark` class directly, has to move: `night` is expressed as `dark night` together. `useTheme` now returns `cycle` rather than `toggle` and reports three schemes.
* the distribution, the import package and the CLI are all `indikit`; the environment prefix is `INDIKIT_`; the npm packages are `@indikit/client` and `@indikit/react`; and the driver property `NEXUS_CONFIG_PERSISTED` is now `INDIKIT_CONFIG_PERSISTED`. Nothing was ever published under the old names, so no upgrade path is provided.
* **a11y:** `AlertAnnouncer` is renamed to `StatusAnnouncer`. It now announces three things and only one of them is an alert: a vector entering Alert, an operator-initiated write reaching a settled state, and connection loss or recovery. The new name matches the `role="status"` it renders.
* **react:** DeviceConfigCard and DeviceConfigCardProps are removed from @indi-nexus/react and replaced by DeviceConfigDialog and DeviceConfigDialogProps. The card was deleted rather than kept alongside the dialog: nothing used it once the panel stopped pinning it, and two components rendering identical copy is the pair that drifts.
* **web:** Bridge.add_sink, remove_sink and snapshot are replaced by attach() returning a Subscription; a browser may no longer send def, set, message or delProperty; and serve refuses a non-loopback host without --token or --allow-insecure-bind.
* **client:** send() and its helpers raise NotConnectedError when disconnected rather than queueing, unsent messages are discarded when a connection ends, and wait_for returns a copy rather than the live vector.
* **protocol:** timestamps on Vector, Message and DelProperty are timezone-aware UTC, so comparing one against a naive datetime.now() raises TypeError. A naive datetime passed to prop.set(timestamp=) or device.message(timestamp=) is read as UTC, not local. parse_indi() no longer raises on a malformed value; it returns fewer messages, and the count is on the parser. format_number changes at exact half ticks.

### Added

* add a logging, settings and observability surface ([d94064d](https://github.com/sidereal-software/indikit/commit/d94064d3dcbeb5bf27dc617c20cc0c2ce4a7dce4))
* add an exception hierarchy rooted at IndiError ([efdb046](https://github.com/sidereal-software/indikit/commit/efdb046925a8f022dcc581ea31226f4fdf4d0ba2))
* **cli:** add Typer serve/run/monitor commands ([e583d5e](https://github.com/sidereal-software/indikit/commit/e583d5eb80d9dc2824012bfd11053e5d1d2b21d1))
* **client:** add onWrite so a consumer can tell its writes from telemetry ([0c91fab](https://github.com/sidereal-software/indikit/commit/0c91fab9664111ca7a5328d83895f110eb544a20))
* **client:** add PropertyStore cache with subscriptions ([56e7950](https://github.com/sidereal-software/indikit/commit/56e795026dbce8a3111d4f4bca9fc7d78b1143c8))
* **client:** add public send() for forwarding messages upstream ([9c573dd](https://github.com/sidereal-software/indikit/commit/9c573dd4d6587611f956b02a532ccb13f260e985))
* **client:** add reconnecting IndiClient ([82a4cee](https://github.com/sidereal-software/indikit/commit/82a4ceeaedbded855afd39a70c8e5730d429c597))
* **cli:** indi-nexus new scaffolds a runnable driver ([c53b24c](https://github.com/sidereal-software/indikit/commit/c53b24c52d3b727b19bc791f3f84593a231738c3))
* **cli:** run drivers in-process with serve --device ([e19f168](https://github.com/sidereal-software/indikit/commit/e19f168101713ab5f0971c4ecba66eb0b44df75a))
* **demo:** replace three demo pages with one observatory wallboard ([f9145e2](https://github.com/sidereal-software/indikit/commit/f9145e208d6e73aec7dd19014db593210c27ee08))
* **docker:** ship an image with indiserver, the bridge and the panel ([6d0e212](https://github.com/sidereal-software/indikit/commit/6d0e2120d97e8ef314ede7d59a18a39ba58470ea))
* **docs:** add a live weather demo running in the browser ([da64737](https://github.com/sidereal-software/indikit/commit/da6473735649265121b2562f8ccb51a59254fb6f))
* **docs:** MkDocs Material site with live demo, both APIs, Pages deploy ([1da18e4](https://github.com/sidereal-software/indikit/commit/1da18e4e87928f0156c6a701184a16ad70a74aef))
* **docs:** rebuild the weather demo around the real panel and a proper dashboard ([a6c8d2d](https://github.com/sidereal-software/indikit/commit/a6c8d2daa34f3735fb628c004d9dd6138930542a))
* **docs:** redesign the custom UI as a dome wallboard ([cf67168](https://github.com/sidereal-software/indikit/commit/cf671681cbd97e0ba82a2ed081c81dc81ca2c769))
* **docs:** repaint the site in an astronomy palette that passes AA ([5b916bb](https://github.com/sidereal-software/indikit/commit/5b916bb22d68ac6ff6194463deb793677f111de8))
* **driver:** add [@every](https://github.com/every) and [@on](https://github.com/on)_new decorators ([a9ee27e](https://github.com/sidereal-software/indikit/commit/a9ee27ecee498cddfb82f5c0d28dde4b5f83076d))
* **driver:** add BoundProperty and Device base class ([4a9f7b3](https://github.com/sidereal-software/indikit/commit/4a9f7b3501aafc7571ad5dda623a5a76a2379f0c))
* **driver:** add stdio runtime and package entrypoint ([7a841d8](https://github.com/sidereal-software/indikit/commit/7a841d8f012483143c5eccf975dc67194874a0d1))
* **driver:** built-in CONNECTION lifecycle and connection-gated jobs ([1a32b14](https://github.com/sidereal-software/indikit/commit/1a32b14be14e9f04c2d599e94edc6e7c234c919d))
* **driver:** let a driver save and restore its configuration ([d943a6a](https://github.com/sidereal-software/indikit/commit/d943a6a4269ed93e9286489c8635bf86d04ab7c6))
* **driver:** publish which properties Save will write ([e1b2cc1](https://github.com/sidereal-software/indikit/commit/e1b2cc15e9b5cf3e3dc38c13aa76a655b65eee58))
* **driver:** serialize dispatch, type properties, and quiet the wire ([2824378](https://github.com/sidereal-software/indikit/commit/2824378a9e68a2dd1d66f7bd3b21a053c81cf95e))
* **driver:** serve several devices from one process ([16625d3](https://github.com/sidereal-software/indikit/commit/16625d345ae8a8a31d60b7aa8d0228b0b4a9379c))
* **examples:** add a BLOB receiver and a scripted session client ([3f2f719](https://github.com/sidereal-software/indikit/commit/3f2f71943dca4fa48745f240f97f6e795875d7e8))
* **examples:** add a dome simulator driver ([aefacf1](https://github.com/sidereal-software/indikit/commit/aefacf1b633e5739167f99c1d1b562efff34118f))
* **examples:** add a hardware-shaped weather station driver ([a7da59d](https://github.com/sidereal-software/indikit/commit/a7da59d0b73306c4a2c4159b2b6abb4fa86e481d))
* **examples:** add a telescope simulator driver ([90ebb9e](https://github.com/sidereal-software/indikit/commit/90ebb9e259496e93d2a79a6f91d988685295e56e))
* **examples:** add an Open-Meteo driver for real public data ([4a6def5](https://github.com/sidereal-software/indikit/commit/4a6def52e38c93ac4b4e0a5f8b5f877821defbb1))
* **examples:** gate the dome behind CONNECTION; test both simulators ([3a9bc9a](https://github.com/sidereal-software/indikit/commit/3a9bc9a0aca8d5efe43409e808ce80c523e5233f))
* **examples:** port libindi's CCD Simulator to the SDK ([2f0626a](https://github.com/sidereal-software/indikit/commit/2f0626ab847697b18809d9928bf2b56d310b8ad4))
* **examples:** publish wind bearing and apparent temperature ([65d92bb](https://github.com/sidereal-software/indikit/commit/65d92bbbb3c6eab4090e9adfbab48349ff4f2944))
* **examples:** serve any driver in the demo bridge via --device ([463826e](https://github.com/sidereal-software/indikit/commit/463826e3db131df9383d3df2979caca89bd56fcc))
* **examples:** serve several drivers in one panel ([c3a325f](https://github.com/sidereal-software/indikit/commit/c3a325fbfbfccc055a0e883ada07a5bdb6ee549f))
* **panel:** animate the messages rail and use a bottom drawer on mobile ([da4804d](https://github.com/sidereal-software/indikit/commit/da4804d75779d44296a0f9fa2c5890cff11f6931))
* **panel:** backend-less demo build with an in-browser dome simulator ([460f072](https://github.com/sidereal-software/indikit/commit/460f072594a08313128781dc179c34dabc055cb2))
* **panel:** disclose the messages panel from its own title bar ([705a33a](https://github.com/sidereal-software/indikit/commit/705a33ad106830e42690fcd2a84031c5e65db0e3))
* **panel:** dock the message log as a right-hand sidebar ([c57e596](https://github.com/sidereal-software/indikit/commit/c57e596b7a60840bf364fd68181b2aa292486d73))
* **panel:** dock the message log as a VS Code-style bottom panel ([69a87f4](https://github.com/sidereal-software/indikit/commit/69a87f44d63e9945b57e51b81ab4532f1f5804e1))
* **panel:** dock the messages log as a collapsible side panel ([47ff543](https://github.com/sidereal-software/indikit/commit/47ff5431ad8b2aa01800549a8790caa58779150a))
* **panel:** move the messages toggle into the sidebar menu ([d147f04](https://github.com/sidereal-software/indikit/commit/d147f04fb0cf9d152e956ce8127c07931caeb0fc))
* **panel:** navbar-height messages bar, unread badge, and tooltips ([721e6c9](https://github.com/sidereal-software/indikit/commit/721e6c96422388f41388752b10cd2536fb058b90))
* **panel:** toggle the messages sidebar from a header icon button ([007f781](https://github.com/sidereal-software/indikit/commit/007f781a1de2a551588e424fb74fc653f1ed67dd))
* **protocol:** add enableBLOB message and BLOBPolicy ([60f3c08](https://github.com/sidereal-software/indikit/commit/60f3c085410600c93b6f58ec52bbe7db1e60b420))
* **protocol:** add JSON codec and base64 BLOB serialization ([8195c92](https://github.com/sidereal-software/indikit/commit/8195c9266e303708a52fda9219f3fbcf95cf08b3))
* **protocol:** add slugify and Element.from_labels ([97b067f](https://github.com/sidereal-software/indikit/commit/97b067ffa693256adade71cc7b444fc6ff085290))
* **protocol:** add typed INDI protocol core with XML codec ([c39975a](https://github.com/sidereal-software/indikit/commit/c39975ab101a8447242e540c1346e84a6e381c77))
* **protocol:** inflate a zlib-compressed BLOB on the way in ([a2bb2fc](https://github.com/sidereal-software/indikit/commit/a2bb2fc966f5e36eee259725fbf919ef25184077))
* **protocol:** pure vector accessors for handler ergonomics ([fe5af28](https://github.com/sidereal-software/indikit/commit/fe5af288e194840b08b49761080e1b94fcfcd1e5))
* **react:** add per-kind value hooks ([28f27a2](https://github.com/sidereal-software/indikit/commit/28f27a20e6fb3075b55c219be65a91ea8eebd79d))
* **react:** add the shadcn accordion primitive ([5341f4f](https://github.com/sidereal-software/indikit/commit/5341f4f13e405b5a4a18821c178c2e9e3ce32d5b))
* **react:** add the shadcn drawer primitive ([9180b8f](https://github.com/sidereal-software/indikit/commit/9180b8f16b5ce728b21789105612315632e6c853))
* **react:** export the test harness as @indi-nexus/react/testing ([8440709](https://github.com/sidereal-software/indikit/commit/8440709cf6978b8e8d34d9b6d244b7c28e34ae9c))
* **react:** give CONFIG_PROCESS a card that tells the truth ([e526d11](https://github.com/sidereal-software/indikit/commit/e526d11d43c8065963088b361802b61a03993f51))
* **react:** move configuration to a sidebar entry and a modal ([d3506f1](https://github.com/sidereal-software/indikit/commit/d3506f1c25874b360349c66a64e942f8751fedeb))
* **testing:** add DeviceHarness ([a737146](https://github.com/sidereal-software/indikit/commit/a737146755651b88049c1a6d8fdcd63a71628e5f))
* **theme:** a blue action, and a red safelight for night ([0bb3dcc](https://github.com/sidereal-software/indikit/commit/0bb3dcce4e2157301e6df3ead5e521db0f0f132f))
* **theme:** commit the Emission Spectrum identity across three schemes ([e2d9092](https://github.com/sidereal-software/indikit/commit/e2d909248661c4ab0d1c434c844299691d5ba54c))
* **theme:** self-host the faces, and let value carry the write action ([58e427f](https://github.com/sidereal-software/indikit/commit/58e427f292a7e30149c52e349eb0fa2f97abb0f8))
* **theme:** the selected switch member wears the action colour ([1875524](https://github.com/sidereal-software/indikit/commit/1875524b78fcbb1316abdf748187ae51ab0a1c38))
* **web:** add @indi-nexus/client transport and property store ([6c77924](https://github.com/sidereal-software/indikit/commit/6c779246a67615d3edd2bc5b5f57e11dcd3f0c0b))
* **web:** add @indi-nexus/react hooks and shadcn/ui components ([c46ab2d](https://github.com/sidereal-software/indikit/commit/c46ab2d9474b084f77630e5a18d2f9aba374a189))
* **web:** add Bridge and FastAPI app (WebSocket + REST snapshot) ([5048e91](https://github.com/sidereal-software/indikit/commit/5048e9177aa44e44a7debb006928e57435fdadb1))
* **web:** add self-contained debug inspector page ([f6441b9](https://github.com/sidereal-software/indikit/commit/f6441b9ffb1db6d743d761dc8ee745f00eaf8c5b))
* **web:** add the reference panel app ([2d7e9c2](https://github.com/sidereal-software/indikit/commit/2d7e9c2edafcb1b8ab63802b07ba30d4be6bde2a))
* **web:** count a coalesced BLOB, and record why the bridge coalesces ([a36bf66](https://github.com/sidereal-software/indikit/commit/a36bf663a86f575a91f6ab4ceb09d30400b57bac))
* **web:** debug-info display setting for technical INDI detail ([f38af6f](https://github.com/sidereal-software/indikit/commit/f38af6f4297cdc72b747aaca8165f88a38bae971))
* **web:** live current-value readouts on writable elements ([c631c1e](https://github.com/sidereal-software/indikit/commit/c631c1e0468239fed416255fb586fcc2efd0f8c3))
* **web:** mark the selected switch in the action colour and pulse Busy ([cf55441](https://github.com/sidereal-software/indikit/commit/cf554417fc66c103499a85e057de38cf9d800226))
* **web:** serve the built panel from FastAPI; add demo bridge harness ([eff8e1a](https://github.com/sidereal-software/indikit/commit/eff8e1a588d4d318c98453c9dea12eafc5a634e6))
* **web:** stack message-log entries and follow the newest ([cd91cdf](https://github.com/sidereal-software/indikit/commit/cd91cdfd05a42dd9449e320aaca28fab4ba396b2))
* **web:** useElement hook for single-value reads ([b1623cf](https://github.com/sidereal-software/indikit/commit/b1623cf3436bf857965ab3ae76259d4b395f7755))
* **web:** version the browser JSON contract with a hello frame ([6a4333a](https://github.com/sidereal-software/indikit/commit/6a4333ac00400652ca3f65649d35909a46802548))


### Fixed

* **a11y:** correct contrast, targets and motion from theme.css ([d37ca55](https://github.com/sidereal-software/indikit/commit/d37ca558033ede615659a7d7db482d1ca48451df))
* **build:** keep node_modules out of the sdist and the package sources in ([718abd2](https://github.com/sidereal-software/indikit/commit/718abd24febf31c62526e7e9646698edb45bc1c0))
* **ci:** build workspace packages before typecheck and test ([072e32f](https://github.com/sidereal-software/indikit/commit/072e32f3e33ad08b8b706d150e85d2a73e697571))
* **ci:** give Mermaid a browser to render diagrams with ([aa92a79](https://github.com/sidereal-software/indikit/commit/aa92a790e656f7c4d4362baf81b4b600a47a881a))
* **ci:** pin pnpm in the release workflow too ([f3242ac](https://github.com/sidereal-software/indikit/commit/f3242ac95af7bfbb2d79399daaaef33230280dc3))
* **ci:** pin pnpm version for pnpm/action-setup ([e977c47](https://github.com/sidereal-software/indikit/commit/e977c473f34311f2150479df6d62b5e4e034a815))
* **ci:** pin setup-uv to a tag that exists ([965440c](https://github.com/sidereal-software/indikit/commit/965440ccb04785d2b4993eb8928cef6f1b887834))
* **ci:** smoke-test the image through its own token guard ([2afb6b8](https://github.com/sidereal-software/indikit/commit/2afb6b8ca690e71a3c25bd7599331b9e707007ef))
* **client:** fall back to the element name when a label is blank ([a887fbf](https://github.com/sidereal-software/indikit/commit/a887fbfdcd29bdd94c9e0e283d940792f199193d))
* **client:** ignore a socket that has already been superseded ([7b4d0e2](https://github.com/sidereal-software/indikit/commit/7b4d0e283f134032c7500a1eb10cde5640b64b2a))
* **client:** keep a property's state when a set does not carry one ([dfa9a46](https://github.com/sidereal-software/indikit/commit/dfa9a4652099f0863642966a1c4f13b3bb12357d))
* **client:** key BLOB policies on a pair, and drop non-object frames ([ff2d87e](https://github.com/sidereal-software/indikit/commit/ff2d87e5ec91bfe3ad5f7957f76723407f6a80b7))
* **client:** mirror the new protocol rules in the browser store ([398ab0b](https://github.com/sidereal-software/indikit/commit/398ab0b422d333e34059b5a73a43afcdad3fb160))
* **client:** refuse a send while disconnected instead of queueing it ([fff3cfb](https://github.com/sidereal-software/indikit/commit/fff3cfb9c79eaacaac7a917f04375faea27d26b0))
* **client:** render numbers the way the wire renders them ([9903f21](https://github.com/sidereal-software/indikit/commit/9903f216257752a333f67bdf89d9d3c13d5c6237))
* **client:** stop a reconnect timer orphaning a live socket ([cfa0311](https://github.com/sidereal-software/indikit/commit/cfa0311555ae28a784f80f6e9c5ef6b367900cdf))
* **demo:** put the simulators back in step with their drivers ([0c475d8](https://github.com/sidereal-software/indikit/commit/0c475d83568a72256999783f168d6fa41407126a))
* **driver:** coerce or refuse a value at assignment, not in the writer ([9f4fca7](https://github.com/sidereal-software/indikit/commit/9f4fca788a6c88de4a048c44d64426a3f6fa7846))
* **driver:** emit a detached copy of a vector, not the live one ([40c9953](https://github.com/sidereal-software/indikit/commit/40c9953f5ec475ea183e95035bf01d3796439d6c))
* **driver:** gate [@every](https://github.com/every) jobs on setup() completion ([7ceeabd](https://github.com/sidereal-software/indikit/commit/7ceeabdb11ba3949d46657084f90ca411f4dd61d))
* **driver:** honor the getProperties device filter ([856768b](https://github.com/sidereal-software/indikit/commit/856768b5eeb90af1862b32fbc9964ba3fc5daacd))
* **driver:** ignore client writes addressed to other devices ([31ad723](https://github.com/sidereal-software/indikit/commit/31ad723fb2eb749c61ca2838add941cb2055c608))
* **driver:** remove a property when it is deleted, as libindi does ([c5d3292](https://github.com/sidereal-software/indikit/commit/c5d32921f63338722e738820c6344593f0e7e4f9))
* **driver:** stop on a write failure and never half-apply a set ([73ae266](https://github.com/sidereal-software/indikit/commit/73ae266085d455d7d2261c42b6034caaef9c6f31))
* **driver:** survive exceptions from [@on](https://github.com/on)_new handlers and setup() ([cce961f](https://github.com/sidereal-software/indikit/commit/cce961fc276c89939f89de237c59625f062825a4))
* **examples:** give the demo device a connection switch ([3effeb7](https://github.com/sidereal-software/indikit/commit/3effeb7dffc70e751ec2c49660c69f6fa8c4b785))
* **examples:** give the flat panel a connection switch ([732870d](https://github.com/sidereal-software/indikit/commit/732870de08b941271ea3b93cae61e4546da6b9f5))
* **examples:** power-gate the demo animation and accept partial switch writes ([95d1c99](https://github.com/sidereal-software/indikit/commit/95d1c999a2714713b62be6db178697864eb05acb))
* **examples:** settle every property when the client disconnects ([deddb7e](https://github.com/sidereal-software/indikit/commit/deddb7e832ea8b170a67c9113594919d926e5162))
* **panel:** give a stop command the one action colour, not its own red ([83e3e71](https://github.com/sidereal-software/indikit/commit/83e3e716ca57099bdba8f5cd442c646cfac1e12b))
* **panel:** keep two theme toggles in step ([6a014c5](https://github.com/sidereal-software/indikit/commit/6a014c5e7316e565ef3b1b7b6a7e3f6c2ef8f25e))
* **panel:** nest configuration under its device, and draw a command as a button ([ba7c8ea](https://github.com/sidereal-software/indikit/commit/ba7c8eac5a3f90e29dd9ea77dab139b61a265203))
* **panel:** unstack configuration from the device list and size the message strip ([bed8ca0](https://github.com/sidereal-software/indikit/commit/bed8ca00ab5b5cdd4571c01d91528ca8e0c5b149))
* **protocol:** close four codec holes and discriminate the message union ([aadbd50](https://github.com/sidereal-software/indikit/commit/aadbd501635d5d40d7923f0afa2f2f8cbb693da3))
* **protocol:** emit standard base64 for a BLOB, not the URL-safe alphabet ([064d1c7](https://github.com/sidereal-software/indikit/commit/064d1c72cd342d7adacb246099c44eaa789c2054))
* **protocol:** make `name in vector` tell the truth ([30275d6](https://github.com/sidereal-software/indikit/commit/30275d63316fb0e9ab932e8d00b913638cf7aebd))
* **protocol:** survive a hostile peer and stamp timestamps in UTC ([bfe2ddf](https://github.com/sidereal-software/indikit/commit/bfe2ddfbc875320b8740f3b4aeba076d8b574f9c))
* **react:** give dark mode a destructive colour and a visible action colour ([ad9bea8](https://github.com/sidereal-software/indikit/commit/ad9bea8425f7fa6bbb88357322bd1ab3c7d52912))
* **react:** make the panel usable without sight or a mouse ([6d39585](https://github.com/sidereal-software/indikit/commit/6d395859eaa9f10d938ede0f86f958c3b45800e7))
* **react:** read an offsetless INDI timestamp as UTC ([3634466](https://github.com/sidereal-software/indikit/commit/3634466547767f42e32007e1dca5d5c13bd55c86))
* **react:** restore pointer cursor on enabled buttons under Tailwind v4 ([42bb085](https://github.com/sidereal-software/indikit/commit/42bb0852b741ae2942d506ef369d5af92bb158a7))
* **tests:** drive the switch vector as buttons, not as a radio group ([0bc1dd8](https://github.com/sidereal-software/indikit/commit/0bc1dd83cc70c474845f5168240e0c55633df997))
* **tests:** give each interop server its own HOME ([a4ec69d](https://github.com/sidereal-software/indikit/commit/a4ec69dea6c6b50ca3ff0c21537ee244bd19e485))
* **theme:** let a card be a surface, not a drawn box ([e1cd3d1](https://github.com/sidereal-software/indikit/commit/e1cd3d1c61e5543a93d82bbb26c2c4054732bb2a))
* **transport:** add close to the transport contract and release sockets ([0fdc210](https://github.com/sidereal-software/indikit/commit/0fdc210debbbc6f75705d6b043ca441b81355b4c))
* **typing:** ship a py.typed marker ([4664027](https://github.com/sidereal-software/indikit/commit/46640271c20b9c77bdcf71f453a6b057bed26a19))
* **web:** a device with no properties is not a missing device ([a74467b](https://github.com/sidereal-software/indikit/commit/a74467b14e01ca2a6643b8770d02edf65ee1d5a9))
* **web:** buffer INDI messages and replay them to late-joining viewers ([93c258e](https://github.com/sidereal-software/indikit/commit/93c258e1550567401dd1ec4b56f652635b05661a))
* **web:** drop the tick and stop a switch deselecting itself ([2fc020d](https://github.com/sidereal-software/indikit/commit/2fc020de622505fdcea94709a6bb272097b93fb9))
* **web:** make the active member of a switch vector legible ([fdfd135](https://github.com/sidereal-software/indikit/commit/fdfd135876964c06ec0791465ac1febe0e9e6835))
* **web:** make the panel and the wallboard work on a phone ([ffc1d7e](https://github.com/sidereal-software/indikit/commit/ffc1d7ecd43d74a56d9a90db4535934b9ab3ac0d))
* **web:** read an empty delProperty name as a named delete in the debug page ([cc2688d](https://github.com/sidereal-software/indikit/commit/cc2688dec5321fadfe6f0c17274cc481d7e8e493))
* **web:** stack writable-element rows so labels and readouts always fit ([aec4436](https://github.com/sidereal-software/indikit/commit/aec443602babc882572018cc4fcf4d031c0a8f11))
* **web:** start the bridge without waiting for indiserver ([e0274f3](https://github.com/sidereal-software/indikit/commit/e0274f345c1e70db7b9d22ed0475e0c73806f450))
* **web:** stop one browser stalling the bridge, and guard /ws ([90d3cb9](https://github.com/sidereal-software/indikit/commit/90d3cb99174230970a4ba9d505f1f64b20aa481b))
* **web:** track src/lib/utils.ts (gitignored by the Python lib/ rule) ([b777e09](https://github.com/sidereal-software/indikit/commit/b777e0924614c7e4c327c38eb2dd6036a81e0650))
* **web:** use relative imports in @indi-nexus/react instead of the @/ alias ([8d1bd3a](https://github.com/sidereal-software/indikit/commit/8d1bd3aa2d72b4a63060529182ed6822863d6e46))


### Performance

* **react:** memoise the property grid ([0c99a33](https://github.com/sidereal-software/indikit/commit/0c99a337820658a39296cab1f70101b8e1129aca))


### Packaging

* add httpx dev dependency and filter starlette test warning ([c2ed83c](https://github.com/sidereal-software/indikit/commit/c2ed83c6500237e5fc178c96437d3d5475ce18bc))
* automate PyPI and npm releases ([097a3b9](https://github.com/sidereal-software/indikit/commit/097a3b9dfdea435e1063f845baac5e3eecf303f1))
* bundle the reference panel into the wheel ([e7dd273](https://github.com/sidereal-software/indikit/commit/e7dd2733eb646a7325f3bf0c40ee1da34a7b9ccf))
* **ci:** move every action off the deprecated Node 20 runtime ([bacd233](https://github.com/sidereal-software/indikit/commit/bacd23390b4324c87e1db28892272f36a72ccffd))
* **docker:** drop the syntax directive so the image builds offline ([806ff3b](https://github.com/sidereal-software/indikit/commit/806ff3b236f6421314b62e6b9564eb06b08a87ab))
* keep breaking changes on the minor while below 1.0 ([1a9d647](https://github.com/sidereal-software/indikit/commit/1a9d6475acc8b39ccccadd160262f103ea7311b3))
* let Release Please own the changelog and drop towncrier ([8a37c37](https://github.com/sidereal-software/indikit/commit/8a37c37ffef52b614301593c51575ebe2693c2ff))
* manage the changelog with towncrier ([990b29b](https://github.com/sidereal-software/indikit/commit/990b29bf70cd8bd8178d3b424f9c4fe25f04ab7e))
* release only the packages that actually changed ([754402c](https://github.com/sidereal-software/indikit/commit/754402c0282516456f52312f4ccb0856128f1162))
* require Python 3.12 and drop the anyio dependency ([128d042](https://github.com/sidereal-software/indikit/commit/128d0427d1515e24f40bdef1486064702a3405db))
* set up Python packaging, dependencies, and dev tooling ([7ff13cd](https://github.com/sidereal-software/indikit/commit/7ff13cd24a74b8db20350a4eea8d9d15828140f1))
* test and declare Python 3.13 and 3.14 ([f962290](https://github.com/sidereal-software/indikit/commit/f962290dba22982f59f281564a383191327348e0))


### Documentation

* add DEVELOPMENT.md with the full command reference ([40a8192](https://github.com/sidereal-software/indikit/commit/40a8192ba64346c0360e05aa408d02db723e9acb))
* add quickstart and command reference to README ([9df062f](https://github.com/sidereal-software/indikit/commit/9df062fbbb92fb902975f972e7463aee38be5ab5))
* add the real-data tutorial and its custom UI ([47980b1](https://github.com/sidereal-software/indikit/commit/47980b1be722591190f17e493fe22c166e50b749))
* adopt Python 3.12, asyncio, and NumPy-docstring conventions ([802a16a](https://github.com/sidereal-software/indikit/commit/802a16abaf0d3a09184d1f71eeb8d0d65ce1b82d))
* capture product truth and document the design system ([bf92d32](https://github.com/sidereal-software/indikit/commit/bf92d3256c2c3eec72cfc4e75bfdf0c2bef5fdf2))
* **claude:** split the guidance by area and add the global working rules ([da96e31](https://github.com/sidereal-software/indikit/commit/da96e31e0a60bdd82884344a89748065683684a8))
* correct the claims this audit disproved ([b91f509](https://github.com/sidereal-software/indikit/commit/b91f509e7b119a0d0102ed3f580f71ea6c0d8293))
* correct the macOS install claim and cut repetition ([a9e8027](https://github.com/sidereal-software/indikit/commit/a9e8027d2198c9b211da33a9a069001b83484127))
* correct the night-mode claim and record what the wire cannot answer ([c5d329b](https://github.com/sidereal-software/indikit/commit/c5d329bd2c917821c6effa242fd8712e0edf0c85))
* cover the new SDK surface, port guide, and mermaid diagrams ([f94fd80](https://github.com/sidereal-software/indikit/commit/f94fd8084c333b9bb9ef82d05340af7c11e46602))
* cut duplication and fix broken cross-references ([44781e8](https://github.com/sidereal-software/indikit/commit/44781e8c157e494d056881cc6eaae9417e17bdac))
* cut the 0.1.0 changelog for today, and write up releasing ([93c1a26](https://github.com/sidereal-software/indikit/commit/93c1a2639d8c1ba618a83aa9da8639ad4de99671))
* describe INDINexus, stack, and workflows in README and CLAUDE.md ([e69104d](https://github.com/sidereal-software/indikit/commit/e69104df8396a4ffaab0e2d4b70073243aaf649e))
* docstring type fields are plain text, not backticked ([300b85a](https://github.com/sidereal-software/indikit/commit/300b85ae46cdb3f7e1a02f058a2f48f512592845))
* document the examples and the three ways to run a driver ([1fc9f03](https://github.com/sidereal-software/indikit/commit/1fc9f03b65af038fa4de9b2c7b70b24e8bfbbee3))
* **driver:** add Numpydoc parameter types to docstrings ([429d920](https://github.com/sidereal-software/indikit/commit/429d920488e147a91bb61561bdc83ae4b9653fca))
* **driver:** document the driver SDK and add demo device ([f9d8dae](https://github.com/sidereal-software/indikit/commit/f9d8dae8eacbae9e0f025a66abeadf3b475bb19f))
* **driver:** NumPy-style docstrings across the driver SDK ([7ed606a](https://github.com/sidereal-software/indikit/commit/7ed606a8fa73517a2a242fbc7a4896057a45c65b))
* drop backticks from docstring type fields ([5c733ee](https://github.com/sidereal-software/indikit/commit/5c733ee830b862f673d9f53fa07fc7f5e5b27c5d))
* drop the docs-domain concern, which is resolved ([76c95dd](https://github.com/sidereal-software/indikit/commit/76c95ddb6fcd0f6f4f6bda8fa4c9cfcabbae3548))
* **examples:** add monitor_client example with tests ([3d1f137](https://github.com/sidereal-software/indikit/commit/3d1f137df55e21dac76a9cec52e51b6100654ddc))
* **examples:** docstring the demo device methods ([f12b7f5](https://github.com/sidereal-software/indikit/commit/f12b7f5a8712d3272a8db325c8cb5fa05ee3f940))
* feature all three simulators in the demo ([6638357](https://github.com/sidereal-software/indikit/commit/66383570d48f5ba4c24a4c25ace11cd920f0ea76))
* fix the claims an audit found were no longer true ([65c8cc9](https://github.com/sidereal-software/indikit/commit/65c8cc9ec053a5a61a780456f05af1013a7fd0f4))
* focus the README on quickstart and link the development guide ([82a9fdc](https://github.com/sidereal-software/indikit/commit/82a9fdce9341e4023d4c4b787cf9f4ddf332cb38))
* general refactor - tighten prose and update project URLs ([7b3b76e](https://github.com/sidereal-software/indikit/commit/7b3b76ea475482f303db84760dcfc11600678150))
* give the examples a reading order instead of a list ([fc34499](https://github.com/sidereal-software/indikit/commit/fc34499d6e7809fe083d672b5e472e888b5a205a))
* give the React layer equal billing and teach with a focuser ([1a6d861](https://github.com/sidereal-software/indikit/commit/1a6d8611b16ca419c94322411208e24438ad7d0a))
* improve mermaid diagram contrast on light backgrounds ([ff1c796](https://github.com/sidereal-software/indikit/commit/ff1c796f8325a3ce5a6ca5581a3d5cff77d5c7e1))
* install from PyPI, and be clear indiserver is the hub ([25bba24](https://github.com/sidereal-software/indikit/commit/25bba241c200b5f922b38c83ac6ec56df2c578d4))
* let the diagrams follow the theme, and validate them in CI ([40152d7](https://github.com/sidereal-software/indikit/commit/40152d75be5b5403159f19a43445c879a76f01b4))
* link the weather demo and give it a nav tab ([893a139](https://github.com/sidereal-software/indikit/commit/893a139b62939fde4484cd2f7827f3ee8f59ae29))
* make the flat-field lamp a real example and run it in the browser ([21ddd52](https://github.com/sidereal-software/indikit/commit/21ddd525c830f7b92c0cd8202c8e2bc0a84f535c))
* make the interop container the default way to run interop ([7e64e17](https://github.com/sidereal-software/indikit/commit/7e64e1713acf3e98ded3bd193956bae1c9537409))
* mark client layer done; refresh README ([8f0d5da](https://github.com/sidereal-software/indikit/commit/8f0d5da3f513c5334494488fe3f7cd14f7b0df50))
* mark M5 done and document the frontend ([e902251](https://github.com/sidereal-software/indikit/commit/e902251b31dba8e8737d61be4031e761a8238f86))
* mark web bridge and CLI done; add bridge E2E and docs ([992d401](https://github.com/sidereal-software/indikit/commit/992d401f186a601b436418740d050c0032e9e275))
* note the libcairo the social-card plugin needs on macOS ([5e6d99d](https://github.com/sidereal-software/indikit/commit/5e6d99d0700d96e9c1d74f4bcd5b5b40d055c403))
* **protocol:** add Numpydoc parameter types to docstrings ([d95cb56](https://github.com/sidereal-software/indikit/commit/d95cb5673d56a2fa2bed26a82d319ed647c366ad))
* **protocol:** NumPy-style docstrings across the protocol layer ([12ae2d9](https://github.com/sidereal-software/indikit/commit/12ae2d922bc0b7ef19bdfda38af87d2bdbf1c2c9))
* reconcile every document with the three new surfaces ([9c5c13c](https://github.com/sidereal-software/indikit/commit/9c5c13c050c4d5b0270acf4ae37774d58fb3a690))
* reconcile the guides with a milestone they missed ([d7be286](https://github.com/sidereal-software/indikit/commit/d7be2863722d5cc93413499bcdd409408d9faad1))
* reconcile the guides, the register and the conventions ([bdb2571](https://github.com/sidereal-software/indikit/commit/bdb2571bec68919c8b58f40096b4e7b7a41bb928))
* record that the docs domain is only half moved ([b079528](https://github.com/sidereal-software/indikit/commit/b079528bf02696c8296f4c4e95c6193f8065d63f))
* record the fourth breaking change in the release register ([0cefc89](https://github.com/sidereal-software/indikit/commit/0cefc895a654c44f14b9d2c25359941291d1e22d))
* record the nightly interop suite failing since 2026-08-18 ([bea1b39](https://github.com/sidereal-software/indikit/commit/bea1b39747abb928527abd19c51a9292f06e39bc))
* record the third red interop night, and the third local pass ([71857eb](https://github.com/sidereal-software/indikit/commit/71857ebf0ccd65d36c2f78431119232c0ea48876))
* require a connection switch in every example and simulator ([bebb26a](https://github.com/sidereal-software/indikit/commit/bebb26af5a0cf4b840fca06eeb6b9db1e3bfc56b))
* rewrite the documentation in a plainer voice ([fe99bca](https://github.com/sidereal-software/indikit/commit/fe99bcaab7ff20e01f19291781266930adc3e6ea))
* rewrite the guides and READMEs in a plainer tone ([d6ad6cd](https://github.com/sidereal-software/indikit/commit/d6ad6cdd7e3fad2146ae609a31c36d7c9caee04e))
* rewrite the landing page for someone who has written a driver ([25f2484](https://github.com/sidereal-software/indikit/commit/25f24849d90b755258310d7da3c4cd6ef25b613f))
* rewrite the public docs for a first-time reader ([02abc5c](https://github.com/sidereal-software/indikit/commit/02abc5cbef6542154cc72a50e36bce3c214c63bd))
* say what a BLOB's format suffixes mean ([2b10d7f](https://github.com/sidereal-software/indikit/commit/2b10d7ff765c38259d9f6051b0efb927bdc059ea))
* serve the live demo as its own page and move the site to a subdomain ([f7fd934](https://github.com/sidereal-software/indikit/commit/f7fd93494bf72291e8833d86e5c1da53ed39e241))
* specify Numpydoc parameter formatting rules ([79c7554](https://github.com/sidereal-software/indikit/commit/79c7554d9895096d0a6c0b6869aab79a05763772))
* split the changelog into sections and publish it on the docs site ([e91502e](https://github.com/sidereal-software/indikit/commit/e91502e254a0f5558952d8ddde3455e4528d33be))
* start a concern register ([42c965b](https://github.com/sidereal-software/indikit/commit/42c965b3aaa9e55b26b077eae21670c485dc9b44))
* **tests:** add NumPy-style docstrings to the test suite ([0bcb910](https://github.com/sidereal-software/indikit/commit/0bcb91042ed9d05ad8e3cd0da6a3aaf5f302ffc8))
* **tests:** type the docstring parameter entries in the suite ([7b2c470](https://github.com/sidereal-software/indikit/commit/7b2c470ed7598cc26a4483c03c5778f9615589da))
* tighten CLAUDE.md and point it at DEVELOPMENT.md ([73509ad](https://github.com/sidereal-software/indikit/commit/73509ad496d60b8d2d20ea3d4b0ec8ac817fc1a6))
* update CLAUDE.md for the transport, runtime, and bridge changes ([79b9b93](https://github.com/sidereal-software/indikit/commit/79b9b9368d299af72fe7b646dfd6ef18fab645a5))
* **web:** add readmes and licences to the published npm packages ([169e304](https://github.com/sidereal-software/indikit/commit/169e304853614769b349644bc7e4a065a5e460ac))


### Changed

* **cli:** read the whole INDI_NEXUS_* environment through Settings ([e403a2a](https://github.com/sidereal-software/indikit/commit/e403a2a76ab3c602e762a033f1eebd449baf7b4a))
* **driver:** extract shared transport contract ([bbfb996](https://github.com/sidereal-software/indikit/commit/bbfb9967a1a0630597dd9eb5dac86bf8d4119cbc))
* **driver:** replace anyio with asyncio in the runtime ([7f65305](https://github.com/sidereal-software/indikit/commit/7f65305b6439eec32b34dafeccd7886d8a4bed81))
* **examples:** adopt the SDK connection surface and accessors ([00cb80d](https://github.com/sidereal-software/indikit/commit/00cb80d65f7b73220febd253677a955b2b5d75f2))
* move InProcessHub out of web/ and share the number helpers ([2cd54d1](https://github.com/sidereal-software/indikit/commit/2cd54d1779c32e736b63a853383b3f1385b54799))
* **protocol:** use stdlib StrEnum for the wire enums ([e4ff825](https://github.com/sidereal-software/indikit/commit/e4ff82537023d5bb4cae3cb92463339b2eab85ab))
* rename the project to INDIkit ([1b5cfd6](https://github.com/sidereal-software/indikit/commit/1b5cfd629a17ffd08c92866df6604ddf79b95c73))
* **settings:** take the config directory from click, not by hand ([40699a6](https://github.com/sidereal-software/indikit/commit/40699a683df1f20949ead1a4fe51f80e4f8e59e4))
* **web:** map an INDI state to its colour in one place ([2084e66](https://github.com/sidereal-software/indikit/commit/2084e669ebc94622dadc7b938bfa206273da3df5))

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
