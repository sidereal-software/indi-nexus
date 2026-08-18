---
search:
  boost: 2
---

# Porting a pyINDI driver

[pyINDI](https://github.com/so-mops/pyINDI) mirrors the libindi C API in Python:
`ISGetProperties`, the four `ISNew*` methods, `IUFind`, `IDSet`,
`@device.repeat`. INDINexus keeps the same INDI semantics and replaces that
vocabulary with plain Python. A port is mostly mechanical, and this page is the
mapping.

Property names, element names, labels and groups can all stay exactly as they
are, so an existing client or panel sees the same device before and after.

## The mapping

| pyINDI | INDINexus |
|---|---|
| `class Device(device)` | `class MyDriver(Device)` |
| `ISGetProperties(self, device)` | `async def setup(self)` |
| `ISwitchVector(sw, dev, name, state, rule, perm, 0, label, group)` | `self.define_switch(name, sw, rule=..., label=..., group=...)` |
| `INumberVector(...)` / `ITextVector(...)` / `ILightVector(...)` | `define_number` / `define_text` / `define_light` |
| `IBLOBVector(...)` / `IBLOB` | `self.define_blob(name, [BLOB(name=...)], perm=IPerm.RO)` |
| `saveConfigItems` / `IUSaveConfig*` | `persist=True` on the `define_*` call, plus `self.define_config()` once |
| `loadConfig()` / `IULoadDefaultSwitches` | `await self.load_config()`, and `on_config_loaded(names)` to act on what came back |
| `self.IDDef(vp)` | (implicit - `define_*` emits the `def`) |
| `self.IUFind("name")` | `self["name"]`, or `self.switch("name")` for a typed handle |
| `vp["el"].value = x` then `self.IDSet(vp)` | `self["name"].set(el=x, state=...)` |
| `ISNewSwitch/Number/Text(self, device, name, values, names)` | `@on_new("name")` per property |
| `values`/`names` parallel lists | one parsed, typed vector; `vector.selected()`, `vector.get(el, default)` |
| `@device.repeat(1000)` | `@every(seconds=1)` |
| `self.IDMessage("...")` | `self.message("...")` / `self.log_error("...")` |
| `sk = Device(name=...)` then `sk.start()` at import | `if __name__ == "__main__": MyDriver.run()` |
| no connection property | `self.define_connection()` + `on_connect` / `on_disconnect` |
| (untestable without hardware) | `DeviceHarness` |

## What changes beyond the names

Defining a property is one call rather than two: `define_*` registers it and
emits its `def`. The argument order that differs per vector class in pyINDI
(`ILightVector` has no `perm`, so everything after it shifts) becomes
keyword-only arguments with one shape.

Client writes arrive parsed, one handler per property. Instead of four `ISNew*`
methods demultiplexing on `name`, tag one method per property with
`@on_new("name")`. It receives the vector the client sent, so there are no
parallel `values`/`names` lists to zip back together.

Updates are atomic. In pyINDI you mutate `.value` on elements and then remember
to `IDSet(vp)`; forgetting it, or typing `==` where you meant `=`, silently does
nothing. `set(...)` writes the elements and emits the update together, or not at
all.

Importing a driver module runs nothing. A pyINDI driver file ends by
constructing and starting a device at module scope, which is why a test cannot
import it. An INDINexus driver is a class, and `run()` happens under
`if __name__ == "__main__"`.

Blocking hardware calls need `off_thread`. pyINDI's callbacks are synchronous,
so a blocking instrument call was merely slow; here it stalls the event loop.
See [Talking to real hardware](writing-drivers.md#talking-to-real-hardware).

Failures are isolated. A raising handler or poll tick is reported to the client
and swallowed, rather than killing a task and leaving the UI frozen on stale
values.

Configuration is declared, not written. libindi picks the subset to persist
inside `saveConfigItems`, so which properties Save covers is buried in a method
and invisible on the wire. Here you mark each one where it is defined -
`define_*(..., persist=True)` - and call `define_config()` once to publish the
`CONFIG_PROCESS` switch. Because the choice is declarative, the SDK can also
publish the answer as `NEXUS_CONFIG_PERSISTED`, which a panel reads to name what
Save writes. Restoring stays yours: `await self.load_config()` where you want the
I/O to happen, and `on_config_loaded(names)` to act on the values it applied. See
[Saving configuration](writing-drivers.md#saving-configuration).

## A worked fragment

pyINDI:

```python
def ISGetProperties(self, device=None):
    commands = [ISwitch("open", ISState.OFF, "Open"),
                ISwitch("close", ISState.OFF, "Close")]
    svp = ISwitchVector(commands, MYDEVICE, "commands", IPState.IDLE,
                        ISRule.ATMOST1, IPerm.RW, 0, "Commands", "Main Control")
    self.IDDef(svp)

def ISNewSwitch(self, device, name, values, names):
    if name == "commands":
        svp = self.IUUpdate(device, name, values, names)
        if svp["open"].value == "On":
            ok = hardware.open()
            if not ok:
                svp.state = IPState.ALERT
                svp["open"].value = "Off"
        self.IDSet(svp)

@device.repeat(1000)
def update(self):
    try:
        tvp = self.IUFind("states")
    except ValueError:
        return
    ...
```

INDINexus:

```python
async def setup(self) -> None:
    self.define_switch(
        "commands",
        [Switch(name="open", label="Open"), Switch(name="close", label="Close")],
        rule=ISRule.AT_MOST_ONE,
        label="Commands",
        group="Main Control",
    )

@on_new("commands")
async def _commands(self, vector: SwitchVector) -> None:
    pressed = vector.selected()
    if pressed is None:
        return
    self["commands"].set({pressed: ISState.ON}, state=IPState.BUSY)
    if not await self.off_thread(getattr(hardware, pressed)):
        self["commands"].set({pressed: ISState.OFF}, state=IPState.ALERT)
        self.log_error(f"Failed to {pressed}")

@every(seconds=1)
async def update(self) -> None:
    ...                      # self["states"] cannot fail to resolve
```

## Then add tests

This is the part with no pyINDI equivalent. A driver that could only be
exercised against the instrument itself now runs in a test in milliseconds. See
[Testing without hardware](writing-drivers.md#testing-without-hardware), and
`tests/test_weather_example.py` for a full worked set.
