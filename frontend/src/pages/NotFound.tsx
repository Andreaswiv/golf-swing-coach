import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="card mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl">Page not found</h1>
      <p className="mt-2 text-mute">
        That address does not exist.{" "}
        <Link to="/" className="link">
          Go to your swings
        </Link>
        .
      </p>
    </div>
  );
}
