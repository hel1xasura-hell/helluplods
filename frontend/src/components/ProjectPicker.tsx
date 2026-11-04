import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { Project } from "../types/api";
import { inputClass } from "./ui";

/** Project selector kept in the URL (?project=...). Returns the selected project id. */
export function useProjectId(projects: Project[] | null): [string, (id: string) => void] {
  const [params, setParams] = useSearchParams();
  const id = params.get("project") ?? projects?.[0]?.id ?? "";
  return [id, (next) => setParams({ project: next })];
}

export function ProjectPicker({ projects, value, onChange }: { projects: Project[]; value: string; onChange: (id: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-medium">Project</span>
      <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </label>
  );
}

export function useProjects() {
  return useApi(api.projects);
}
