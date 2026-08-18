/** The libindi properties that are the driver's own machinery, not the instrument's. */

/**
 * Property names {@link DevicePanel} folds away into "Driver internals".
 *
 * Every libindi driver carries a handful of properties that are about the driver
 * process rather than about the instrument: its debug plumbing, the devices it
 * snoops on, and where its configuration lives. They arrive scattered through
 * whichever group the driver put them in - usually "Options", beside settings an
 * operator does want - and they are the properties a night operator never
 * touches. Ekos keeps the same list and hides it outright; the panel folds it
 * instead, so it is one click away rather than gone.
 *
 * `CONNECTION` is on Ekos' list and deliberately **not** here. It is the one
 * control every operator reaches for first, and a device that will not connect is
 * the commonest thing to be looking at, so burying it behind a disclosure would
 * hide the most-used button on the panel to tidy away the least-used ones. Ekos
 * can drop it because it drives connection from its own toolbar; the panel has no
 * such second home for it.
 *
 * `CONFIG_PROCESS` is here because {@link DeviceConfigDialog} already offers it
 * from the sidebar - folding it as well would draw it twice. So is
 * `NEXUS_CONFIG_PERSISTED`, the one entry no libindi driver publishes: an
 * INDINexus driver lists there which of its properties Save writes, which the
 * same dialog renders as a sentence. A layout that draws it anyway shows an
 * operator a read-only field of wire names.
 *
 * Exported so a consumer building its own layout can ask the same question the
 * panel asks. There is deliberately no prop to override it: the answer is a fact
 * about libindi, not a preference.
 */
// `ReadonlySet` and not `Object.freeze`: freezing a Set seals its own properties
// and leaves `add`/`delete` working, so it would promise more than it delivers.
export const DRIVER_MACHINERY: ReadonlySet<string> = new Set([
  "DEBUG",
  "SIMULATION",
  "CONFIG_PROCESS",
  "NEXUS_CONFIG_PERSISTED",
  "ACTIVE_DEVICES",
  "DEBUG_LEVEL",
  "LOGGING_LEVEL",
  "LOG_OUTPUT",
  "FILE_DEBUG",
]);
