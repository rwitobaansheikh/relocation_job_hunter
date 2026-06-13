import { useCallback, useRef, useState } from 'react'

const HOVER_DELAY_MS = 550

/**
 * Button with an extended-hover help card. On touch devices, tap the ℹ icon.
 */
export default function HelpButton({
  help,
  title,
  children,
  className = '',
  helpPlacement = 'top',
  ...buttonProps
}) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const show = useCallback(() => {
    clearTimer()
    timerRef.current = setTimeout(() => setVisible(true), HOVER_DELAY_MS)
  }, [clearTimer])

  const hide = useCallback(() => {
    clearTimer()
    setVisible(false)
  }, [clearTimer])

  const toggleTouch = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setVisible((v) => !v)
  }, [])

  if (!help) {
    return (
      <button type="button" className={className} {...buttonProps}>
        {children}
      </button>
    )
  }

  return (
    <span
      className={`help-button-wrap help-placement-${helpPlacement}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <button type="button" className={className} {...buttonProps}>
        {children}
      </button>
      <button
        type="button"
        className="help-touch-trigger"
        aria-label="What does this button do?"
        onClick={toggleTouch}
      >
        ℹ
      </button>
      {visible && (
        <div className="help-card" role="tooltip">
          {title && <div className="help-card-title">{title}</div>}
          <p className="help-card-text">{help}</p>
        </div>
      )}
    </span>
  )
}
