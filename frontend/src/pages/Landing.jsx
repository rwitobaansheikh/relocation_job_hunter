import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { ContactSection, ReviewsSection } from '../components/Feedback'

const FEATURES = [
  {
    title: 'All-in-one job search',
    body: 'Search LinkedIn, RemoteOK, Remotive, We Work Remotely and more from a single dashboard — filtered by your CV and target roles.',
  },
  {
    title: 'AI-tailored CVs & cover letters',
    body: 'Every job gets a CV360-style ATS CV and cover letter rewritten for the role — preview, edit, and download as Word docs.',
  },
  {
    title: 'SMTP-verified email outreach',
    body: 'Find recruiter and HR emails for each company — verified against their mail server — then send tailored outreach from your inbox.',
  },
  {
    title: 'Bulk document tailoring',
    body: 'Tailor documents for dozens of discovered jobs in one click, then apply on job sites or email recruiters directly.',
  },
  {
    title: 'AI role suggestions',
    body: 'Upload your CV and get tailored job-title suggestions — use them as-is or combine with your own target roles.',
  },
  {
    title: 'Match scoring & analysis',
    body: 'See how well each role fits your background before you spend time tailoring and applying.',
  },
  {
    title: 'Application tracking',
    body: 'Track every job from discovered → tailored → applied → interview in one pipeline view.',
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
        <div className="brand-logo" style={{ fontSize: '1.5rem' }}>
          <img src="/logo-small.png" alt="Logo" />
          <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
        </div>
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
        <div className="landing-hero__badge">3-day free trial · Search · Tailor · Outreach</div>
        <h1>Find jobs. Tailor your CV. Reach hiring teams.</h1>
        <p>
          Job Application Flow brings job search, AI document tailoring, and email outreach into one workspace —
          discover roles, generate tailored CVs and cover letters, find recruiter emails, and apply your way.
        </p>
        <div className="landing-cta">
          <button className="btn-primary" onClick={() => navigate('/register')}>Start free trial</button>
          <button className="btn-secondary" onClick={() => navigate('/login')}>I already have an account</button>
        </div>
      </header>

      <h2 className="section-heading">Everything you need to run an aggressive job search</h2>
      <p className="section-sub">One workspace from job search to tailored documents to outreach and apply.</p>
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
        <div className="card"><h3>1. Upload your CV</h3><p>Upload your CV — we suggest job roles from your experience, or enter your own target titles and locations.</p></div>
        <div className="card"><h3>2. Search jobs</h3><p>Run a search across multiple job boards. Every match is saved to your Applications pipeline automatically.</p></div>
        <div className="card"><h3>3. Tailor documents</h3><p>The AI generates a CV360-style ATS CV and cover letter tailored to each job description.</p></div>
        <div className="card"><h3>4. Outreach or apply</h3><p>Find verified recruiter emails and send outreach from your inbox, or apply directly on the job site — track status as you go.</p></div>
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
