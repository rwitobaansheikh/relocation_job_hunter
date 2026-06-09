import { ContactSection, ReviewsSection } from '../components/Feedback'

export default function Feedback() {
  return (
    <div>
      <h2 className="page-title">Feedback & Contact</h2>
      <p className="page-subtitle">Tell us how it's going, or get in touch with the team.</p>
      <ReviewsSection />
      <ContactSection />
    </div>
  )
}
