import { Link } from "react-router-dom";
import { PageHeader, Panel } from "../components/ui";
import { NAV } from "../nav";

export default function More() {
  return (
    <>
      <PageHeader title="All sections" />
      <Panel>
        <ul className="divide-y divide-line">
          {NAV.map((n) => (
            <li key={n.path}>
              <Link to={n.path} className="flex min-h-14 items-center gap-3 px-4 hover:bg-raised">
                <n.icon className="size-5 text-mute" aria-hidden /><span>{n.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
