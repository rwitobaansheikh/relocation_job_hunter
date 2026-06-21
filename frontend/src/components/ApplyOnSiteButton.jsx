import HelpButton from './HelpButton'

/**
 * Opens the job listing in a new tab and optionally marks the application as applied.
 */
export default function ApplyOnSiteButton({
  jobUrl,
  onApply,
  disabled = false,
  busy = false,
  className = 'btn-primary',
  size = '',
  label = 'Apply on job site',
}) {
  if (!jobUrl) {
    return (
      <button type="button" className={`${className} ${size}`.trim()} disabled title="No job listing URL">
        No listing URL
      </button>
    )
  }

  return (
    <HelpButton
      className={`${className} ${size}`.trim()}
      disabled={disabled || busy}
      onClick={onApply}
      title={label}
      help="Opens the original job posting in a new tab so you can submit your tailored CV and cover letter manually."
    >
      {busy ? 'Opening…' : label}
    </HelpButton>
  )
}
