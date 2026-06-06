import { NavLink, Route, Routes } from 'react-router-dom'
import { ProfileProvider } from './ProfileContext'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import Jobs from './pages/Jobs'
import Applications from './pages/Applications'

export default function App() {
  return (
    <ProfileProvider>
      <div className="layout">
        <nav className="sidebar">
          <h1>Job Hunter</h1>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/profile">Profile & Uploads</NavLink>
          <NavLink to="/jobs">Search Jobs</NavLink>
          <NavLink to="/applications">Applications</NavLink>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/applications" element={<Applications />} />
          </Routes>
        </main>
      </div>
    </ProfileProvider>
  )
}
