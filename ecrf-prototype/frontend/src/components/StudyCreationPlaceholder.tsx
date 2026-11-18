import { useId } from "react";

export default function StudyCreationPlaceholder({ onClose }: { onClose: () => void }) {
  const formId = useId();
  return <form className="card study-create" onSubmit={(event) => event.preventDefault()} aria-labelledby={`${formId}-title`}>
    <h2 className="section-title" id={`${formId}-title`}>Create a study</h2>
    <p className="muted small mb-4">Study creation is not connected yet; nothing can be saved here.</p>
    <div className="grid-2">
      <div><label className="label" htmlFor={`${formId}-name`}>Study name</label><input className="input" id={`${formId}-name`} disabled /></div>
      <div><label className="label" htmlFor={`${formId}-code`}>Study ID</label><input className="input" id={`${formId}-code`} disabled /></div>
    </div>
    <div className="row mt-4"><button className="btn btn-teal" type="submit" disabled>Create study</button><button className="btn btn-secondary" type="button" onClick={onClose}>Cancel</button></div>
  </form>;
}
