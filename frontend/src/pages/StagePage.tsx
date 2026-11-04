import { useLocation } from "react-router-dom";
import { NAV } from "../nav";
import { PageHeader, Panel, Pill } from "../components/ui";

/** Honest placeholder for sections whose backend is not built yet. It states what is missing. */
export default function StagePage() {
  const { pathname } = useLocation();
  const item = NAV.find((n) => n.path === pathname);
  if (!item) return <PageHeader title="Page not found" />;
  return (
    <>
      <PageHeader title={item.label} subtitle={item.purpose} />
      <Panel className="p-6">
        <Pill tone="warn">Not built yet</Pill>
        <p className="mt-3 max-w-prose text-sm">
          This section is scheduled for Stage {item.stage}. Nothing here is simulated: until it ships, there is no data
          and no controls to show.
        </p>
      </Panel>
    </>
  );
}
