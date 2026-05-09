import { Link } from 'react-router-dom'

export function NotFound(): React.ReactElement {
  return (
    <section>
      <h1>404 — Not Found</h1>
      <p>The requested page does not exist.</p>
      <p>
        <Link to="/">Return to dashboard</Link>
      </p>
    </section>
  )
}

export default NotFound
