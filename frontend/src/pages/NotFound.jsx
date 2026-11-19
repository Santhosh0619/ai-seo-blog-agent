import { Link } from "react-router-dom";
import { Logo } from "../ui";

export default function NotFound() {
  return (
    <div className="notfound fade-up"><div>
      <Logo />
      <h1 className="display grad-text" style={{ marginTop: 28 }}>404</h1>
      <p className="muted" style={{ margin: "10px 0 22px" }}>We could not find that page.</p>
      <Link className="btn btn-primary" to="/">Back to home</Link>
    </div></div>
  );
}
