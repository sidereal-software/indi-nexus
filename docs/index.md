# INDINexus

A modern, typed Python framework for
[INDI](http://www.clearskyinstitute.com/INDI/INDI.pdf) astronomical instrument
control. Write drivers in clean async Python, watch them from a typed client,
and put a polished React UI in front of your observatory - all on one shared,
validated protocol model.

<div class="grid cards" markdown>

- **Drivers in Python**

    Subclass `Device`, declare properties, poll with `@every`, handle writes
    with `@on_new`. The standard INDI lifecycle - connection, dispatch,
    supervision - is built in.

    [Write your first driver](guides/writing-drivers.md)

- **React components & hooks**

    `@indi-nexus/client` speaks the wire; `@indi-nexus/react` turns any INDI
    device into a live, themed UI with hooks like `useProperty` and components
    like `DevicePanel`.

    [Build a frontend](guides/frontend.md)

</div>

## See it live

The real INDINexus panel, running against a **simulated dome driver entirely
in your browser** - no server behind it. Connect the dome, open the shutter,
send it to an azimuth, park it, and watch the INDI message log narrate.

[Launch the live demo](demo-app/index.html){ .md-button .md-button--primary }

## The stack

```mermaid
flowchart LR
    subgraph py["Python (indi_nexus)"]
        drv["Driver SDK<br/><code>driver/</code>"]
        cli["IndiClient<br/><code>client/</code>"]
        web["FastAPI bridge<br/><code>web/</code>"]
    end
    hw(["Instrument"]) --- drv
    drv -- "stdio<br/>INDI 1.7 XML" --> hub["<b>indiserver</b><br/>C hub, :7624"]
    hub -- "TCP<br/>INDI 1.7 XML" --> cli
    cli --> web
    web -- "WebSocket<br/>typed JSON" --> ui["React panel<br/>or your UI"]

    classDef ext fill:#eee,stroke:#999,color:#333
    class hub,hw,ui ext
```

- **Keep C `indiserver` as the hub** - existing INDI drivers and clients
  interoperate; INDINexus modernizes the Python and browser layers.
- **Dual protocol** - canonical INDI 1.7 XML on the wire, typed JSON to
  browsers, one Pydantic model as the shared contract.
- **Fully typed** - `mypy --strict` Python, TypeScript end to end.

## Quick taste

```python
from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import IPState, Number

class Mount(Device):
    name = "Mount"

    async def setup(self) -> None:
        self.define_connection()
        self.define_number(
            "EQUATORIAL_EOD_COORD",
            [Number(name="RA", format="%9.6m"), Number(name="DEC", format="%9.6m")],
        )

    @every(seconds=1, when_connected=True)
    async def poll(self) -> None:
        ra, dec = await self.read_mount()
        self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec, state=IPState.OK)
```

```tsx
import { IndiProvider, useElement, DevicePanel } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <DevicePanel device="Mount" />
  </IndiProvider>
);
```

[Get started](getting-started.md){ .md-button .md-button--primary }
[Browse the Python API](reference/python/driver.md){ .md-button }
