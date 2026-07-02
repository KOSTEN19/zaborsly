import AuthenticatedImage from "./AuthenticatedImage";

interface PhotoModalProps {
  url: string | null;
  title: string;
  onClose: () => void;
}

export default function PhotoModal({ url, title, onClose }: PhotoModalProps) {
  if (!url) return null;

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-4xl">
        <h3 className="font-bold text-lg mb-4">{title}</h3>
        <AuthenticatedImage url={url} alt={title} className="w-full rounded-lg" />
        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop" onClick={onClose}>
        <button>close</button>
      </form>
    </dialog>
  );
}
