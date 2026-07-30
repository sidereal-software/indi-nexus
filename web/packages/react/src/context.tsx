/**
 * React context wiring for an {@link IndiClient}.
 *
 * `IndiProvider` owns (or accepts) a single client, connects it on mount and
 * closes it on unmount, and makes it available to the hooks and components via
 * context. Passing an existing `client` (already constructed, e.g. in a test or a
 * custom setup) takes precedence over the inline connection `options`.
 */

import { IndiClient, type IndiClientOptions } from "@indi-nexus/client";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

const IndiContext = createContext<IndiClient | null>(null);

/** Props for {@link IndiProvider}. */
export interface IndiProviderProps extends IndiClientOptions {
  /** An existing client to use; overrides the inline connection options. */
  client?: IndiClient;
  children: ReactNode;
}

/**
 * Provide an {@link IndiClient} to descendant hooks and components.
 *
 * @param props - Connection options (or an existing `client`) plus children.
 * @returns The context provider element.
 */
export function IndiProvider({ client, children, ...options }: IndiProviderProps): ReactNode {
  // Only construct a client when one was not supplied - constructing one requires
  // a URL (or a DOM `location`), which a caller-supplied client may not have.
  const [ownedClient] = useState(() => (client ? null : new IndiClient(options)));
  const instance = client ?? ownedClient;
  if (instance === null) {
    throw new Error("IndiProvider requires either a `client` or connection options.");
  }

  useEffect(() => {
    instance.connect();
    return () => instance.close();
  }, [instance]);

  return <IndiContext.Provider value={instance}>{children}</IndiContext.Provider>;
}

/**
 * Return the {@link IndiClient} from the nearest {@link IndiProvider}.
 *
 * @returns The provided client.
 * @throws If called outside an `IndiProvider`.
 */
export function useIndiClient(): IndiClient {
  const client = useContext(IndiContext);
  if (client === null) {
    throw new Error("useIndiClient must be used within an <IndiProvider>.");
  }
  return client;
}
