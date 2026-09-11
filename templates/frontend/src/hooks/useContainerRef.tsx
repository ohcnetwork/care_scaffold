import { createContext, useContext, useRef } from "react";

/**
 * Radix portals (Dialog, Popover, Select, DropdownMenu, Tooltip) render into document.body,
 * escaping the plugin's scoped Tailwind container. Pass this ref as their `container` target
 * so portalled content stays inside the scope and picks up plugin styles.
 */
const ContainerRefContext =
  createContext<React.RefObject<HTMLDivElement | null> | null>(null);

export const useContainerRef = () => {
  const context = useContext(ContainerRefContext);
  if (!context) {
    throw new Error("useContainerRef must be used within a ContainerRefProvider");
  }
  return context;
};

export const ContainerRefProvider: React.FC<{
  children: (ref: React.RefObject<HTMLDivElement | null>) => React.ReactNode;
}> = ({ children }) => {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <ContainerRefContext.Provider value={ref}>
      {children(ref)}
    </ContainerRefContext.Provider>
  );
};
