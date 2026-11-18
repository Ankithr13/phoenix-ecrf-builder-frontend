import { Link } from "react-router-dom";

export default function FeatureUnavailable({ title }: { title: string }) {
  return <div className="page">
    <div className="page-head"><h1 className="page-title">{title}</h1></div>
    <div className="card"><h2 className="section-title">This section is not available in this version</h2><p className="muted small">Your existing protocols remain available.</p><Link className="btn btn-secondary btn-sm mt-4" to="/sponsor/protocols">View protocols</Link></div>
  </div>;
}
