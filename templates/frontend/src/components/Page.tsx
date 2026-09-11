import type { PropsWithChildren } from "react";

import { ContainerRefProvider } from "@/hooks/useContainerRef";

import "@/style/index.css";

/**
 * Scopes plugin Tailwind so it cannot leak into the host.
 * `display: contents` keeps the wrapper out of the host's layout flow.
 *
 * Wrap EVERY root this plugin renders — each extension-point component and each route.
 * The ref is the portal target for Radix components, which would otherwise escape the scope.
 */
export default function Page({ children }: PropsWithChildren) {
  return (
    <ContainerRefProvider>
      {(ref) => (
        <div
          ref={ref}
          className="__PLUGIN_CONTAINER__"
          style={{ display: "contents" }}
        >
          {children}
        </div>
      )}
    </ContainerRefProvider>
  );
}
