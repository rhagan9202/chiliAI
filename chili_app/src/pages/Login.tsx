import { API_BASE_URL } from '../lib/apiClient'

export function Login(): React.ReactElement {
  const handleSignIn = (): void => {
    window.location.assign(`${API_BASE_URL}/auth/login`)
  }

  return (
    <main className="login-page">
      <div className="login-card">
        <h1>chiliAI</h1>
        <p>Please sign in to continue.</p>
        <button type="button" onClick={handleSignIn}>
          Sign in
        </button>
      </div>
    </main>
  )
}

export default Login
