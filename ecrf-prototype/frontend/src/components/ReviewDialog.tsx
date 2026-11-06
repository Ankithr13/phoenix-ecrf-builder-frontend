import { useEffect, useRef, type ReactNode } from "react";

export default function ReviewDialog({ title, onStay, children }: {
  title: string; onStay: () => void; children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog ref={dialogRef} className="review-dialog" aria-labelledby="review-dialog-title" onCancel={(event) => { event.preventDefault(); onStay(); }}>
      <h2 id="review-dialog-title" className="section-title">{title}</h2>
      {children}
    </dialog>
  );
}
