/**
 * `@indi-nexus/react/testing` - render INDI-aware components without a server.
 *
 * The frontend counterpart to Python's `indi_nexus.testing`: render your
 * component against a client wired to a fake socket, feed it the frames a
 * driver would send, and assert on what appears.
 *
 * ```tsx
 * const { socket } = renderConnected(<MyPanel />);
 * receive(socket, { tag: "def", vector: myVector });
 * expect(screen.getByText("120")).toBeInTheDocument();
 * ```
 */

// Re-exported from the same @testing-library/react instance renderConnected
// uses: importing cleanup from a consumer's own copy leaves a second registry
// of mounted containers, and the DOM accumulates between tests.
export { cleanup, screen, within } from "@testing-library/react";
export { FakeSocket } from "./fake-socket";
export { type ConnectedRender, receive, renderConnected } from "./render";
