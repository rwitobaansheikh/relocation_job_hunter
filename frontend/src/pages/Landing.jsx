import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { ContactSection, ReviewsSection } from '../components/Feedback'

const FEATURES = [
  {
    title: 'Smart job discovery',
    body: 'Scans LinkedIn, RemoteOK, Remotive, We Work Remotely and more for fresh roles that match your CV, target roles and locations.',
  },
  {
    title: 'AI role suggestions',
    body: 'Upload your CV and get tailored job-title suggestions — use them as-is or combine with your own target roles.',
  },
  {
    title: 'AI-tailored CVs & cover letters',
    body: 'Every application gets a one-page CV and cover letter rewritten for the job description and rendered as a polished, recruiter-ready PDF.',
  },
  {
    title: 'Verified contact finding',
    body: 'Finds HR and hiring contacts by scraping company careers pages, job listings, and web search — no paid email APIs.',
  },
  {
    title: 'Personalised outreach',
    body: 'Generates compelling, genuinely personalised emails per contact — no placeholders, ever — and sends them from your own mailbox.',
  },
  {
    title: 'Hands-free automation',
    body: 'Set up loops per job role and let the platform search, tailor, and send on a schedule — with strict daily caps and rate limiting.',
  },
]

export default function Landing() {
  const { user } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()

  if (user) return <Navigate to="/app" replace />

  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="brand">Job Application Flow</div>
        <div className="links">
          <a href="#reviews" className="nav-anchor">Reviews</a>
          <a href="#contact" className="nav-anchor">Contact</a>
          <button type="button" className="btn-secondary theme-toggle-nav" onClick={toggleTheme}>
            {theme === 'dark' ? '☀ Light' : '☾ Dark'}
          </button>
          <Link to="/login"><button className="btn-secondary">Log in</button></Link>
          <Link to="/register"><button className="btn-primary">Get started</button></Link>
        </div>
      </nav>

      <header className="landing-hero">
        <h1>Search, tailor, and apply — on autopilot</h1>
        <p>
          Job Application Flow finds roles that fit your background, tailors your CV and cover letter
          to each one, finds the right people to email, and runs the whole application loop for you.
        </p>
        <div className="landing-cta">
          <button className="btn-primary" onClick={() => navigate('/register')}>Create free account</button>
          <button className="btn-secondary" onClick={() => navigate('/login')}>I already have an account</button>
        </div>
      </header>

      <h2 className="section-heading">Everything you need to run an aggressive job search</h2>
      <p className="section-sub">One workspace from discovery to outreach to follow-up.</p>
      <div className="feature-grid">
        {FEATURES.map((f) => (
          <div key={f.title} className="card">
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </div>

      <h2 className="section-heading">How it works</h2>
      <div className="feature-grid">
        <div className="card"><h3>1. Upload your CV</h3><p>Upload your CV and cover letter — we'll suggest job roles based on your experience, or you can enter your own.</p></div>
        <div className="card"><h3>2. Connect your mailbox</h3><p>Add your SMTP sending identity in Settings so outreach goes out from your own email address.</p></div>
        <div className="card"><h3>3. Search & tailor</h3><p>Run a search and let the AI tailor documents and draft outreach for the best-matched roles.</p></div>
        <div className="card"><h3>4. Turn on automation</h3><p>Set up automation loops per role — the platform keeps searching, tailoring and sending within your plan limits.</p></div>
      </div>

      <div style={{ textAlign: 'center', marginTop: '3rem' }}>
        <button className="btn-primary" onClick={() => navigate('/register')} style={{ padding: '0.75rem 1.8rem', fontSize: '1rem' }}>
          Get started — it's free
        </button>
      </div>

      <ReviewsSection />
      <ContactSection />
    </div>
  )
}
