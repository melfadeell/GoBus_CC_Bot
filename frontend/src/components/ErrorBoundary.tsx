import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/** Catches render errors so a single broken component doesn't blank the whole app. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error:', error, info)
  }

  handleReload = () => {
    this.setState({ hasError: false })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '60vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.75rem',
            color: 'var(--color-text-default)',
            fontFamily: 'inherit',
            padding: '2rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>Something went wrong</div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
            Please reload the page. If the problem persists, contact support.
          </div>
          <button type="button" className="btn-accent" onClick={this.handleReload}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
