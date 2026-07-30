# Live demo

The real INDINexus reference panel, running against a **simulated dome
driver entirely in your browser** - there is no server behind this page.

Connect the dome, open the shutter, send it to an azimuth, park it, and watch
the INDI message log narrate. Toggle *Debug info* in the sidebar to see the
raw INDI property names.

<iframe src="demo-app/index.html" title="INDINexus live demo"
        style="width: 100%; height: 720px; border: 1px solid #8884; border-radius: 8px;"></iframe>

The panel is the stock `@indi-nexus/react` app; the "driver" is a small
TypeScript stand-in for `examples/dome_device.py` speaking the same JSON
contract through a fake WebSocket. Against a real observatory the identical
UI talks to `indiserver` through the FastAPI bridge.
