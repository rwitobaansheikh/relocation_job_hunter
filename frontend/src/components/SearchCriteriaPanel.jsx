import { SENIORITY_OPTIONS, POSTED_OPTIONS } from '../constants/search'

const postedLabel = (hours) =>
  POSTED_OPTIONS.find((o) => o.value === hours)?.label || `Last ${hours} hours`

export default function SearchCriteriaPanel({
  criteria,
  selectedRoles,
  selectedLocations,
  selectedSeniority,
  onToggleRole,
  onToggleLocation,
  onToggleSeniority,
  onApplyProfile,
  onApplySearch,
  applySearchLabel = 'Use for job search',
  applying,
}) {
  if (!criteria?.roles?.length) return null

  return (
    <div className="criteria-panel">
      {criteria.summary && (
        <p className="criteria-summary">{criteria.summary}</p>
      )}

      <div className="criteria-block">
        <div className="criteria-label">Suggested roles</div>
        <div className="checkbox-row">
          {criteria.roles.map((role) => (
            <label key={role} className="checkbox-pill">
              <input
                type="checkbox"
                checked={selectedRoles.has(role)}
                onChange={() => onToggleRole(role)}
              />
              {role}
            </label>
          ))}
        </div>
      </div>

      {criteria.locations?.length > 0 && (
        <div className="criteria-block">
          <div className="criteria-label">Suggested locations</div>
          <div className="checkbox-row">
            {criteria.locations.map((loc) => (
              <label key={loc} className="checkbox-pill">
                <input
                  type="checkbox"
                  checked={selectedLocations.has(loc)}
                  onChange={() => onToggleLocation(loc)}
                />
                {loc}
              </label>
            ))}
          </div>
        </div>
      )}

      {criteria.seniority_levels?.length > 0 && (
        <div className="criteria-block">
          <div className="criteria-label">Suggested seniority</div>
          <div className="checkbox-row">
            {SENIORITY_OPTIONS.filter((o) => criteria.seniority_levels.includes(o.value)).map((opt) => (
              <label key={opt.value} className="checkbox-pill">
                <input
                  type="checkbox"
                  checked={selectedSeniority.has(opt.value)}
                  onChange={() => onToggleSeniority(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="criteria-meta muted">
        Posted within: <strong>{postedLabel(criteria.posted_within_hours)}</strong>
        {criteria.min_salary != null && (
          <> · Min salary: <strong>{criteria.min_salary.toLocaleString()}</strong></>
        )}
        {criteria.max_salary != null && (
          <> · Max salary: <strong>{criteria.max_salary.toLocaleString()}</strong></>
        )}
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.9rem', flexWrap: 'wrap' }}>
        {onApplyProfile && (
          <button type="button" className="btn-primary" style={{ fontSize: '0.85rem' }} onClick={onApplyProfile} disabled={applying}>
            Apply to profile
          </button>
        )}
        {onApplySearch && (
          <button type="button" className="btn-secondary" style={{ fontSize: '0.85rem' }} onClick={onApplySearch} disabled={applying}>
            {applySearchLabel}
          </button>
        )}
      </div>
    </div>
  )
}

export const SEARCH_CRITERIA_KEY = 'jaf_search_criteria'

export function saveSearchCriteriaForJobs(criteria, selected) {
  const payload = {
    roles: criteria.roles.filter((r) => selected.roles.has(r)),
    locations: criteria.locations.filter((l) => selected.locations.has(l)),
    seniority_levels: criteria.seniority_levels.filter((s) => selected.seniority.has(s)),
    posted_within_hours: criteria.posted_within_hours,
    min_salary: criteria.min_salary,
    max_salary: criteria.max_salary,
  }
  sessionStorage.setItem(SEARCH_CRITERIA_KEY, JSON.stringify(payload))
  return payload
}
