import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function Projects() {
  const { data, error, loading, reload } = useApi(api.projects);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [execution, setExecution] = useState("cloud");
  const [publishing, setPublishing] = useState("approval");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setFormError(null);
    try {
      await api.createProject({ name, description: description || undefined, execution_mode: execution, publishing_mode: publishing });
      setName(""); setDescription("");
      await reload();
    } catch (err) { setFormError(err instanceof Error ? err.message : "Couldn't create the project"); }
    finally { setBusy(false); }
  }

  async function remove(id: string, projectName: string) {
    if (!window.confirm(`Delete "${projectName}" and its research targets? This can't be undone.`)) return;
    try { await api.deleteProject(id); await reload(); }
    catch (err) { setFormError(err instanceof Error ? err.message : "Couldn't delete the project"); }
  }

  return (
    <>
      <PageHeader title="Projects" subtitle="Each project is one tutorial or series, from research to upload." />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Panel>
          {loading ? <Loading /> : error ? <div className="p-4"><Notice tone="error">{error}</Notice></div> :
            data && data.length > 0 ? (
              <ul className="divide-y divide-line">
                {data.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{p.name}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <Pill tone="mute">{p.status}</Pill>
                        <Pill tone="mute">{p.execution_mode}</Pill>
                        <Pill tone="mute">{p.publishing_mode === "approval" ? "needs approval" : "automatic"}</Pill>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Link to={`/research?project=${p.id}`} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4 text-sm hover:bg-raised">Add targets</Link>
                      <Button variant="danger" onClick={() => void remove(p.id, p.name)}>Delete</Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : <Empty title="No projects yet" hint="Create your first project to start adding sites and apps to research." />}
        </Panel>

        <Panel className="h-fit p-4">
          <h2 className="mb-3 text-lg font-semibold">New project</h2>
          <form className="space-y-3" onSubmit={create}>
            {formError && <Notice tone="error">{formError}</Notice>}
            <Field label="Name"><input className={inputClass} required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Description"><textarea className={`${inputClass} py-2`} rows={3} maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <Field label="Where browsers run">
              <select className={inputClass} value={execution} onChange={(e) => setExecution(e.target.value)}>
                <option value="cloud">Cloud</option><option value="local">Local computer</option><option value="both">Both</option>
              </select>
            </Field>
            <Field label="Publishing">
              <select className={inputClass} value={publishing} onChange={(e) => setPublishing(e.target.value)}>
                <option value="approval">Ask me before uploading</option><option value="automatic">Upload automatically</option>
              </select>
            </Field>
            <Button type="submit" className="w-full" loading={busy}>Create project</Button>
          </form>
        </Panel>
      </div>
    </>
  );
}
