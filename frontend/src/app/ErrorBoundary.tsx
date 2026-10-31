import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '../components/ui/button'

type Props = {
  children: ReactNode
  /** When this value changes (e.g. the route), a previously failed subtree is given another chance. */
  resetKey?: string
}

type State = { error: Error | null }

/**
 * Last line of defence: a render error in one screen shows a recoverable message
 * instead of unmounting the whole application into a blank page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="mx-auto mt-16 flex max-w-lg flex-col items-start gap-3 rounded-2xl border border-critical/25 bg-white p-6 shadow-md">
        <h1 className="text-lg font-semibold">Something went wrong on this screen</h1>
        <p className="text-[0.95rem] text-muted">Your data is safe. You can try again, or go back to the dashboard.</p>
        <div className="flex gap-2">
          <Button onClick={() => this.setState({ error: null })}>Try again</Button>
          <Button variant="secondary" onClick={() => window.location.assign('/')}>Go to dashboard</Button>
        </div>
      </div>
    )
  }
}
