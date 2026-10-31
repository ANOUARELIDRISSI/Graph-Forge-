import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="card">
      <div className="empty">
        <h3>Page not found</h3>
        <p className="muted">The workspace page you requested does not exist.</p>
        <Link className="button" to="/">
          Back to overview
        </Link>
      </div>
    </div>
  );
}
